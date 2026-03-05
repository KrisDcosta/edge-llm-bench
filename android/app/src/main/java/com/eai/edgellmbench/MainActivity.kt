package com.eai.edgellmbench

import android.app.ActivityManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.util.Log
import android.view.View
import android.widget.*
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.FileProvider
import androidx.lifecycle.lifecycleScope
import com.arm.aichat.AiChat
import com.arm.aichat.InferenceEngine
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.onCompletion
import java.io.File
import java.io.FileOutputStream

/**
 * Main activity: offline chat + live metrics overlay + benchmark mode + log export.
 *
 * Architecture:
 *   - Uses com.arm.aichat.InferenceEngine (llama.cpp JNI wrapper from lib module)
 *   - Timing measured at Kotlin layer: first token = when first non-empty token emits
 *   - JSONL logging via BenchmarkLogger (schema-valid records)
 */
class MainActivity : AppCompatActivity() {

    // ── Views ─────────────────────────────────────────────────────────────────
    private lateinit var tvModel: TextView
    private lateinit var spinnerQuant: Spinner
    private lateinit var chatView: ScrollView
    private lateinit var tvChat: TextView
    private lateinit var etInput: EditText
    private lateinit var btnSend: Button
    private lateinit var btnLoadModel: Button
    private lateinit var btnBenchmark: Button
    private lateinit var btnExportLog: Button

    // Metrics overlay
    private lateinit var tvTtft: TextView
    private lateinit var tvPrefillTps: TextView
    private lateinit var tvDecodeTps: TextView
    private lateinit var tvE2E: TextView
    private lateinit var tvGenPrefillRatio: TextView
    private lateinit var tvStatus: TextView

    // ── State ─────────────────────────────────────────────────────────────────
    private lateinit var engine: InferenceEngine
    private lateinit var logger: BenchmarkLogger
    private var isModelLoaded = false
    private var currentQuantVariant = "Q4_K_M"
    private var generationJob: Job? = null
    private val chatHistory = StringBuilder()
    private var trialCounter = 0

    // llama.cpp version (from InferenceEngine.systemInfo or build)
    private val llamaVersion = "b${BuildConfig.VERSION_CODE}"

    companion object {
        private const val TAG = "EdgeLLMBench"
        private const val BENCH_PROMPTS = 3    // trials in benchmark mode
        private const val BENCH_N_TOKENS = 128
        private const val DEFAULT_CTX = 512

        private val BENCH_PROMPT_TEXTS = listOf(
            "Answer in one sentence: What is the capital of France?",
            "Summarize in two sentences: The Eiffel Tower is a wrought-iron lattice tower in Paris.",
            "Answer step by step: If you have 3 apples and give away 1, how many remain?",
        )
        private val BENCH_PROMPT_IDS = listOf("qa_short_001", "summarize_short_001", "reasoning_short_001")

        private val QUANT_VARIANTS = listOf("Q2_K", "Q3_K_M", "Q4_K_M", "Q6_K", "Q8_0")
        private val MODEL_SUBDIR = "models"
    }

    // ── Lifecycle ─────────────────────────────────────────────────────────────

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        bindViews()
        setupQuantSpinner()
        setupButtons()

        logger = BenchmarkLogger(this)

        lifecycleScope.launch(Dispatchers.Default) {
            engine = AiChat.getInferenceEngine(applicationContext)
        }

        appendChat("System", "EdgeLLM Bench ready. Load a GGUF model to begin.")
        updateMetricsDisplay(null)
    }

    override fun onDestroy() {
        if (::engine.isInitialized) engine.destroy()
        super.onDestroy()
    }

    // ── View binding ──────────────────────────────────────────────────────────

    private fun bindViews() {
        tvModel = findViewById(R.id.tv_model_info)
        spinnerQuant = findViewById(R.id.spinner_quant)
        chatView = findViewById(R.id.scroll_chat)
        tvChat = findViewById(R.id.tv_chat)
        etInput = findViewById(R.id.et_input)
        btnSend = findViewById(R.id.btn_send)
        btnLoadModel = findViewById(R.id.btn_load_model)
        btnBenchmark = findViewById(R.id.btn_benchmark)
        btnExportLog = findViewById(R.id.btn_export_log)

        tvTtft = findViewById(R.id.tv_ttft)
        tvPrefillTps = findViewById(R.id.tv_prefill_tps)
        tvDecodeTps = findViewById(R.id.tv_decode_tps)
        tvE2E = findViewById(R.id.tv_e2e)
        tvGenPrefillRatio = findViewById(R.id.tv_gen_prefill_ratio)
        tvStatus = findViewById(R.id.tv_status)
    }

    // ── Quant spinner ─────────────────────────────────────────────────────────

    private fun setupQuantSpinner() {
        spinnerQuant.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_item, QUANT_VARIANTS).also {
            it.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        }
        spinnerQuant.setSelection(QUANT_VARIANTS.indexOf("Q4_K_M"))
        spinnerQuant.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>, view: View?, pos: Int, id: Long) {
                currentQuantVariant = QUANT_VARIANTS[pos]
                isModelLoaded = false
                tvModel.text = "Model: not loaded (${currentQuantVariant})"
                appendChat("System", "Variant changed to $currentQuantVariant — reload model.")
            }
            override fun onNothingSelected(parent: AdapterView<*>) {}
        }
    }

    // ── Buttons ───────────────────────────────────────────────────────────────

    private fun setupButtons() {
        btnLoadModel.setOnClickListener { pickGgufFile() }
        btnSend.setOnClickListener { sendUserMessage() }
        btnBenchmark.setOnClickListener { runBenchmarkMode() }
        btnExportLog.setOnClickListener { exportLog() }
    }

    // ── Model loading ─────────────────────────────────────────────────────────

    private val getContent = registerForActivityResult(
        ActivityResultContracts.OpenDocument()
    ) { uri ->
        uri?.let { loadModelFromUri(it) }
    }

    private fun pickGgufFile() {
        getContent.launch(arrayOf("*/*"))
    }

    private fun loadModelFromUri(uri: Uri) {
        setUiBusy("Loading $currentQuantVariant...")
        lifecycleScope.launch(Dispatchers.IO) {
            try {
                val modelFile = copyUriToLocalFile(uri)
                engine.loadModel(modelFile.absolutePath)
                withContext(Dispatchers.Main) {
                    isModelLoaded = true
                    tvModel.text = "Model: ${modelFile.name} (${currentQuantVariant})"
                    setUiReady()
                    appendChat("System", "Model loaded: ${modelFile.name}")
                }
            } catch (e: Exception) {
                Log.e(TAG, "Model load failed", e)
                withContext(Dispatchers.Main) {
                    setUiReady()
                    appendChat("System", "ERROR loading model: ${e.message}")
                }
            }
        }
    }

    private suspend fun copyUriToLocalFile(uri: Uri): File = withContext(Dispatchers.IO) {
        val dir = File(filesDir, MODEL_SUBDIR).also { it.mkdirs() }
        val filename = uri.lastPathSegment?.substringAfterLast('/') ?: "model_${currentQuantVariant}.gguf"
        val dest = File(dir, filename)
        if (!dest.exists()) {
            contentResolver.openInputStream(uri)?.use { ins ->
                FileOutputStream(dest).use { ins.copyTo(it) }
            }
        }
        dest
    }

    // ── Chat + inference ──────────────────────────────────────────────────────

    private fun sendUserMessage() {
        val text = etInput.text.toString().trim()
        if (text.isEmpty()) return
        if (!isModelLoaded) { Toast.makeText(this, "Load a model first", Toast.LENGTH_SHORT).show(); return }

        etInput.text = null
        appendChat("You", text)
        runInference(promptId = "chat", promptText = text, contextLength = DEFAULT_CTX,
            outputLength = 256, trialIndex = trialCounter++, isWarmup = false)
    }

    private fun runInference(
        promptId: String,
        promptText: String,
        contextLength: Int,
        outputLength: Int,
        trialIndex: Int,
        isWarmup: Boolean,
    ) {
        generationJob?.cancel()
        setUiBusy("Generating…")

        val tRequestStart = nowSeconds()
        var tFirstToken = -1.0
        var tokenCount = 0
        val responseBuffer = StringBuilder()
        val inputTokenCount = estimateTokens(promptText)

        // Battery snapshot
        val batteryStart = getBatteryPct()

        generationJob = lifecycleScope.launch(Dispatchers.Default) {
            try {
                engine.sendUserPrompt(promptText, outputLength)
                    .onCompletion { err ->
                        val tLastToken = nowSeconds()
                        val batteryEnd = getBatteryPct()

                        if (err == null && tFirstToken > 0) {
                            val metrics = InferenceMetrics(
                                promptId = promptId,
                                quantVariant = currentQuantVariant,
                                contextLength = contextLength,
                                outputLength = tokenCount,
                                tRequestStart = tRequestStart,
                                tFirstToken = tFirstToken,
                                tLastToken = tLastToken,
                                inputTokens = inputTokenCount,
                                outputTokens = tokenCount,
                                peakRssMb = getPeakRssMb(),
                                batteryStartPct = batteryStart,
                                batteryEndPct = batteryEnd,
                            )
                            if (!isWarmup) logger.logSuccess(metrics, llamaVersion, trialIndex, isWarmup)
                            withContext(Dispatchers.Main) { updateMetricsDisplay(metrics) }
                        } else if (err != null) {
                            logger.logFailure(currentQuantVariant, contextLength, promptId,
                                llamaVersion, trialIndex, isWarmup, "GENERATION_ERROR", err.message ?: "unknown")
                        }
                        withContext(Dispatchers.Main) { setUiReady() }
                    }
                    .collect { token ->
                        if (tFirstToken < 0 && token.isNotEmpty()) {
                            tFirstToken = nowSeconds()
                        }
                        tokenCount++
                        responseBuffer.append(token)
                        withContext(Dispatchers.Main) {
                            // Update chat with streaming response
                            val lines = tvChat.text.toString().trimEnd()
                            tvChat.text = "$lines$token"
                            chatView.post { chatView.fullScroll(ScrollView.FOCUS_DOWN) }
                        }
                    }
                // Add newline after complete response
                withContext(Dispatchers.Main) { tvChat.append("\n\n") }
            } catch (e: CancellationException) {
                // Normal cancellation — ignore
            } catch (e: Exception) {
                Log.e(TAG, "Inference error", e)
                logger.logFailure(currentQuantVariant, contextLength, promptId,
                    llamaVersion, trialIndex, isWarmup, "RUNTIME_ERROR", e.message ?: "unknown")
                withContext(Dispatchers.Main) {
                    appendChat("System", "ERROR: ${e.message}")
                    setUiReady()
                }
            }
        }
    }

    // ── Benchmark mode ────────────────────────────────────────────────────────

    private fun runBenchmarkMode() {
        if (!isModelLoaded) { Toast.makeText(this, "Load a model first", Toast.LENGTH_SHORT).show(); return }
        setUiBusy("Running benchmark…")
        appendChat("System", "Starting benchmark: $BENCH_PROMPTS prompts × ${currentQuantVariant}")

        lifecycleScope.launch {
            // 1 warmup run (not logged)
            appendChat("System", "[warmup]")
            withContext(Dispatchers.IO) {
                runSingleBenchTrial(
                    BENCH_PROMPT_TEXTS[0], BENCH_PROMPT_IDS[0],
                    DEFAULT_CTX, BENCH_N_TOKENS, 0, isWarmup = true
                )
            }
            delay(2000)

            // 3 recorded trials
            for (i in 0 until BENCH_PROMPTS) {
                appendChat("System", "[trial ${i+1}/$BENCH_PROMPTS]")
                withContext(Dispatchers.IO) {
                    runSingleBenchTrial(
                        BENCH_PROMPT_TEXTS[i], BENCH_PROMPT_IDS[i],
                        DEFAULT_CTX, BENCH_N_TOKENS, trialCounter++, isWarmup = false
                    )
                }
                delay(1000)
            }

            withContext(Dispatchers.Main) {
                appendChat("System", "Benchmark complete. Log: ${logger.getOutputPath()}")
                setUiReady()
            }
        }
    }

    private suspend fun runSingleBenchTrial(
        promptText: String, promptId: String,
        contextLength: Int, outputLength: Int,
        trialIndex: Int, isWarmup: Boolean,
    ) = withContext(Dispatchers.Default) {
        val tRequestStart = nowSeconds()
        var tFirstToken = -1.0
        var tokenCount = 0
        val batteryStart = getBatteryPct()

        try {
            engine.sendUserPrompt(promptText, outputLength)
                .collect { token ->
                    if (tFirstToken < 0 && token.isNotEmpty()) tFirstToken = nowSeconds()
                    tokenCount++
                }
            val tLastToken = nowSeconds()
            if (tFirstToken > 0 && !isWarmup) {
                val metrics = InferenceMetrics(
                    promptId = promptId, quantVariant = currentQuantVariant,
                    contextLength = contextLength, outputLength = tokenCount,
                    tRequestStart = tRequestStart, tFirstToken = tFirstToken, tLastToken = tLastToken,
                    inputTokens = estimateTokens(promptText), outputTokens = tokenCount,
                    peakRssMb = getPeakRssMb(), batteryStartPct = batteryStart, batteryEndPct = getBatteryPct(),
                )
                logger.logSuccess(metrics, llamaVersion, trialIndex, isWarmup = false)
                withContext(Dispatchers.Main) { updateMetricsDisplay(metrics) }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Bench trial error", e)
            logger.logFailure(currentQuantVariant, contextLength, promptId, llamaVersion,
                trialIndex, isWarmup, "BENCH_ERROR", e.message ?: "unknown")
        }
    }

    // ── Log export ────────────────────────────────────────────────────────────

    private fun exportLog() {
        val logFile = File(logger.getOutputPath())
        if (!logFile.exists() || logFile.length() == 0L) {
            Toast.makeText(this, "No log data yet — run benchmark first", Toast.LENGTH_SHORT).show()
            return
        }
        val uri = FileProvider.getUriForFile(this, "${packageName}.fileprovider", logFile)
        startActivity(Intent.createChooser(
            Intent(Intent.ACTION_SEND).apply {
                type = "text/plain"
                putExtra(Intent.EXTRA_STREAM, uri)
                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            }, "Export JSONL log"
        ))
    }

    // ── Metrics UI ────────────────────────────────────────────────────────────

    private fun updateMetricsDisplay(m: InferenceMetrics?) {
        if (m == null) {
            tvTtft.text = "TTFT: —"
            tvPrefillTps.text = "Prefill: —"
            tvDecodeTps.text = "Decode: —"
            tvE2E.text = "E2E: —"
            tvGenPrefillRatio.text = "Gen/Prefill: —"
        } else {
            tvTtft.text = "TTFT: %.2fs".format(m.ttftS)
            tvPrefillTps.text = "Prefill: %.1f tok/s".format(m.prefillTps)
            tvDecodeTps.text = "Decode: %.1f tok/s".format(m.decodeTps)
            tvE2E.text = "E2E: %.2fs".format(m.e2eS)
            tvGenPrefillRatio.text = "Gen/Prefill: %.1fx".format(m.genOverPrefill)
        }
    }

    // ── UI state helpers ──────────────────────────────────────────────────────

    private fun setUiBusy(status: String) {
        tvStatus.text = status
        btnSend.isEnabled = false
        btnBenchmark.isEnabled = false
        btnLoadModel.isEnabled = false
    }

    private fun setUiReady() {
        tvStatus.text = if (isModelLoaded) "${currentQuantVariant} ready" else "No model loaded"
        btnSend.isEnabled = isModelLoaded
        btnBenchmark.isEnabled = isModelLoaded
        btnLoadModel.isEnabled = true
    }

    private fun appendChat(role: String, text: String) {
        chatHistory.append("[$role] $text\n\n")
        tvChat.text = chatHistory
        chatView.post { chatView.fullScroll(ScrollView.FOCUS_DOWN) }
    }

    // ── Utils ─────────────────────────────────────────────────────────────────

    private fun nowSeconds(): Double = System.currentTimeMillis() / 1000.0

    private fun estimateTokens(text: String): Int = (text.length / 4).coerceAtLeast(1)

    private fun getBatteryPct(): Float? = try {
        val intent = registerReceiver(null, android.content.IntentFilter(
            android.content.Intent.ACTION_BATTERY_CHANGED
        ))
        val level = intent?.getIntExtra(android.os.BatteryManager.EXTRA_LEVEL, -1) ?: -1
        val scale = intent?.getIntExtra(android.os.BatteryManager.EXTRA_SCALE, -1) ?: -1
        if (level >= 0 && scale > 0) 100f * level / scale else null
    } catch (e: Exception) { null }

    private fun getPeakRssMb(): Double? = try {
        val am = getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
        val mi = ActivityManager.MemoryInfo()
        am.getMemoryInfo(mi)
        val debug = android.os.Debug.MemoryInfo()
        android.os.Debug.getMemoryInfo(debug)
        debug.totalPss / 1024.0  // KB → MB
    } catch (e: Exception) { null }
}
