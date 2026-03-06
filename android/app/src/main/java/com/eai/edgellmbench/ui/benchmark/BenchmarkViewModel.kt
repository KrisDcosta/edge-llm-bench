package com.eai.edgellmbench.ui.benchmark

import android.app.Application
import android.content.Intent
import android.net.Uri
import androidx.core.content.FileProvider
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.eai.edgellmbench.BenchmarkLogger
import com.eai.edgellmbench.InferenceMetrics
import com.eai.edgellmbench.data.repository.InferenceRepository
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

// ── Domain types ─────────────────────────────────────────────────────────────

data class TrialResult(
    val index: Int,
    val promptId: String,
    val quantVariant: String,
    val contextLength: Int,
    val decodeTps: Double,
    val ttftS: Double,
    val outputTokens: Int,
    val isWarmup: Boolean,
)

sealed class BenchmarkStatus {
    object Idle : BenchmarkStatus()
    data class Running(val phase: String, val current: Int, val total: Int) : BenchmarkStatus()
    object Complete : BenchmarkStatus()
}

data class BenchmarkUiState(
    val status: BenchmarkStatus = BenchmarkStatus.Idle,
    val results: List<TrialResult> = emptyList(),
    val activeVariant: String = "Q4_K_M",
    val isModelLoaded: Boolean = false,
    val errorMessage: String? = null,
    val logPath: String? = null,
)

// ── ViewModel ────────────────────────────────────────────────────────────────

class BenchmarkViewModel(application: Application) : AndroidViewModel(application) {

    private val _uiState = MutableStateFlow(BenchmarkUiState())
    val uiState: StateFlow<BenchmarkUiState> = _uiState.asStateFlow()

    private val engineReady = CompletableDeferred<Unit>()
    private var benchJob: Job? = null
    private val logger by lazy { BenchmarkLogger(application) }

    companion object {
        private const val WARMUP_RUNS = 1
        private const val BENCH_RUNS  = 3
        private const val N_TOKENS    = 128
        private const val CTX_LENGTH  = 512
        private const val COOLDOWN_MS = 2_000L

        private val BENCH_PROMPTS = listOf(
            "qa_short_001" to "Answer in one sentence: What is the capital of France?",
            "summarize_001" to "Summarize in two sentences: The Eiffel Tower is a wrought-iron lattice tower in Paris.",
            "reasoning_001" to "Answer step by step: If you have 8 apples and give away 3, how many remain?",
        )
    }

    init {
        viewModelScope.launch(Dispatchers.Default) {
            InferenceRepository.getEngine(application)
            engineReady.complete(Unit)
        }
        viewModelScope.launch {
            InferenceRepository.modelState.collect { ms ->
                _uiState.update { it.copy(activeVariant = ms.variant, isModelLoaded = ms.isLoaded) }
            }
        }
    }

    fun runBenchmark() {
        if (!_uiState.value.isModelLoaded) {
            _uiState.update { it.copy(errorMessage = "Load a model first") }
            return
        }
        benchJob?.cancel()
        _uiState.update { it.copy(status = BenchmarkStatus.Idle, results = emptyList(), errorMessage = null) }

        benchJob = viewModelScope.launch(Dispatchers.Default) {
            engineReady.await()
            val engine  = InferenceRepository.getEngine(getApplication())
            val variant = _uiState.value.activeVariant
            val total   = WARMUP_RUNS + BENCH_RUNS

            try {
                var trialIdx = 0

                // Warmup runs
                repeat(WARMUP_RUNS) { w ->
                    val (promptId, promptText) = BENCH_PROMPTS[0]
                    updateStatus("Warmup ${w + 1}/$WARMUP_RUNS", trialIdx, total)
                    runTrial(engine, promptId, promptText, variant, trialIdx, isWarmup = true)
                    trialIdx++
                    delay(COOLDOWN_MS)
                }

                // Recorded runs
                repeat(BENCH_RUNS) { b ->
                    val (promptId, promptText) = BENCH_PROMPTS[b % BENCH_PROMPTS.size]
                    updateStatus("Trial ${b + 1}/$BENCH_RUNS", trialIdx, total)
                    val result = runTrial(engine, promptId, promptText, variant, trialIdx, isWarmup = false)
                    result?.let { r ->
                        withContext(Dispatchers.Main) {
                            _uiState.update { it.copy(results = it.results + r) }
                        }
                    }
                    trialIdx++
                    if (b < BENCH_RUNS - 1) delay(COOLDOWN_MS)
                }

                withContext(Dispatchers.Main) {
                    _uiState.update { it.copy(
                        status  = BenchmarkStatus.Complete,
                        logPath = logger.getOutputPath(),
                    ) }
                }
            } catch (e: CancellationException) {
                withContext(Dispatchers.Main) { _uiState.update { it.copy(status = BenchmarkStatus.Idle) } }
            } catch (e: Exception) {
                withContext(Dispatchers.Main) {
                    _uiState.update { it.copy(status = BenchmarkStatus.Idle, errorMessage = e.message) }
                }
            }
        }
    }

    fun stopBenchmark() { benchJob?.cancel() }

    fun dismissError() { _uiState.update { it.copy(errorMessage = null) } }

    fun shareLog(): Intent? {
        val path = _uiState.value.logPath ?: return null
        val file = File(path)
        if (!file.exists() || file.length() == 0L) return null
        val uri: Uri = FileProvider.getUriForFile(
            getApplication(), "${getApplication<Application>().packageName}.fileprovider", file,
        )
        return Intent.createChooser(
            Intent(Intent.ACTION_SEND).apply {
                type = "text/plain"
                putExtra(Intent.EXTRA_STREAM, uri)
                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            },
            "Export benchmark JSONL",
        )
    }

    // ── Private helpers ───────────────────────────────────────────────────────

    private suspend fun runTrial(
        engine: com.arm.aichat.InferenceEngine,
        promptId: String,
        promptText: String,
        variant: String,
        trialIndex: Int,
        isWarmup: Boolean,
    ): TrialResult? {
        val tStart = nowSeconds()
        var tFirstToken = -1.0
        var tokenCount  = 0

        return try {
            engine.sendUserPrompt(promptText, N_TOKENS).collect { token ->
                if (tFirstToken < 0 && token.isNotEmpty()) tFirstToken = nowSeconds()
                tokenCount++
            }
            val tEnd = nowSeconds()

            if (tFirstToken > 0) {
                val metrics = InferenceMetrics(
                    promptId      = promptId,
                    quantVariant  = variant,
                    contextLength = CTX_LENGTH,
                    outputLength  = tokenCount,
                    tRequestStart = tStart,
                    tFirstToken   = tFirstToken,
                    tLastToken    = tEnd,
                    inputTokens   = (promptText.length / 4).coerceAtLeast(1),
                    outputTokens  = tokenCount,
                    peakRssMb     = getPeakRssMb(),
                )
                if (!isWarmup) logger.logSuccess(metrics, "compose-v2", trialIndex, isWarmup = false)
                TrialResult(
                    index         = trialIndex,
                    promptId      = promptId,
                    quantVariant  = variant,
                    contextLength = CTX_LENGTH,
                    decodeTps     = metrics.decodeTps,
                    ttftS         = metrics.ttftS,
                    outputTokens  = tokenCount,
                    isWarmup      = isWarmup,
                )
            } else null
        } catch (e: Exception) {
            if (!isWarmup) {
                logger.logFailure(variant, CTX_LENGTH, promptId, "compose-v2",
                    trialIndex, isWarmup, "BENCH_ERROR", e.message ?: "unknown")
            }
            null
        }
    }

    private fun updateStatus(phase: String, current: Int, total: Int) {
        viewModelScope.launch(Dispatchers.Main) {
            _uiState.update { it.copy(status = BenchmarkStatus.Running(phase, current, total)) }
        }
    }

    private fun nowSeconds(): Double = System.currentTimeMillis() / 1000.0

    private fun getPeakRssMb(): Double? = try {
        val mi = android.os.Debug.MemoryInfo()
        android.os.Debug.getMemoryInfo(mi)
        mi.totalPss / 1024.0
    } catch (e: Exception) { null }
}
