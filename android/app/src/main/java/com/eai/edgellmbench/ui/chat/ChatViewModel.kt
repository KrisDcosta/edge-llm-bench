package com.eai.edgellmbench.ui.chat

import android.app.Application
import android.net.Uri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.eai.edgellmbench.BenchmarkLogger
import com.eai.edgellmbench.InferenceMetrics
import com.eai.edgellmbench.data.repository.InferenceRepository
import com.eai.edgellmbench.data.repository.ModelRepository
import android.util.Log
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.onCompletion
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

// ── UI state types ───────────────────────────────────────────────────────────

data class ChatMessage(
    val id: Long = System.nanoTime(),
    val role: String,      // "user" | "assistant" | "system"
    val content: String,
    val isStreaming: Boolean = false,
)

data class LiveMetrics(
    val ttftS: Double? = null,
    val prefillTps: Double? = null,
    val decodeTps: Double? = null,
    val e2eS: Double? = null,
    val peakRssMb: Double? = null,
)

data class ChatUiState(
    val messages: List<ChatMessage> = listOf(
        ChatMessage(
            id = 0L,
            role = "system",
            content = "Edge LLM Bench — load a GGUF model to start chatting.",
        ),
    ),
    val modelName: String = "No model loaded",
    val isModelLoaded: Boolean = false,
    val isLoadingModel: Boolean = false,
    val isGenerating: Boolean = false,
    val currentVariant: String = "Q4_K_M",
    val liveMetrics: LiveMetrics = LiveMetrics(),
    val errorMessage: String? = null,
)

// ── ViewModel ────────────────────────────────────────────────────────────────

class ChatViewModel(application: Application) : AndroidViewModel(application) {

    private val _uiState = MutableStateFlow(ChatUiState())
    val uiState: StateFlow<ChatUiState> = _uiState.asStateFlow()

    private val engineReady = CompletableDeferred<Unit>()
    private var generationJob: Job? = null
    private var trialCounter = 0

    private val logger by lazy { BenchmarkLogger(application) }

    init {
        // Initialise the engine singleton on a background thread, then attempt
        // to restore the last-used model automatically (cold-start auto-load).
        viewModelScope.launch(Dispatchers.Default) {
            InferenceRepository.getEngine(application)
            engineReady.complete(Unit)
            // Try to restore the previously loaded model silently
            val restored = ModelRepository.tryAutoLoad(application)
            if (restored != null) {
                Log.i("ChatViewModel", "Auto-loaded previous model: $restored")
                withContext(Dispatchers.Main) {
                    appendSystemMessage("Auto-loaded: $restored")
                }
            }
        }
        // Keep UI in sync with shared model state
        viewModelScope.launch {
            InferenceRepository.modelState.collect { ms ->
                _uiState.update { ui ->
                    ui.copy(
                        isModelLoaded  = ms.isLoaded,
                        isLoadingModel = ms.isLoading,
                        currentVariant = ms.variant,
                        modelName      = if (ms.isLoaded) "${ms.variant} loaded" else
                                         if (ms.isLoading) "Loading ${ms.variant}…" else
                                         "No model loaded",
                    )
                }
            }
        }
    }

    // ── Model loading ─────────────────────────────────────────────────────────

    fun loadModelFromUri(uri: Uri, variant: String) {
        viewModelScope.launch {
            _uiState.update { it.copy(errorMessage = null) }
            try {
                val filename = ModelRepository.loadFromUri(getApplication(), uri, variant)
                appendSystemMessage("Loaded: $filename")
            } catch (e: Exception) {
                InferenceRepository.markUnloaded()
                _uiState.update { it.copy(errorMessage = "Load failed: ${e.message}") }
            }
        }
    }

    fun selectVariant(variant: String) {
        InferenceRepository.markUnloaded(nextVariant = variant)
        _uiState.update { it.copy(currentVariant = variant) }
    }

    // ── Inference ─────────────────────────────────────────────────────────────

    fun sendMessage(
        text: String,
        outputLength: Int = 256,
        contextLength: Int = 512,
    ) {
        if (text.isBlank() || !_uiState.value.isModelLoaded) return

        generationJob?.cancel()

        val userMsg = ChatMessage(role = "user", content = text)
        val asstId  = System.nanoTime() + 1L
        val asstMsg = ChatMessage(id = asstId, role = "assistant", content = "", isStreaming = true)

        _uiState.update { it.copy(
            messages     = it.messages + userMsg + asstMsg,
            isGenerating = true,
            liveMetrics  = LiveMetrics(),
        ) }

        generationJob = viewModelScope.launch(Dispatchers.Default) {
            engineReady.await()

            val tStart      = nowSeconds()
            var tFirstToken = -1.0
            var tokenCount  = 0
            val buffer      = StringBuilder()

            try {
                InferenceRepository.getEngine(getApplication())
                    .sendUserPrompt(text, outputLength)
                    .onCompletion { err ->
                        val tEnd = nowSeconds()
                        // Finalise the assistant bubble
                        val finalText = buffer.toString()
                        withContext(Dispatchers.Main) {
                            _uiState.update { state ->
                                state.copy(
                                    messages = state.messages.map { m ->
                                        if (m.id == asstId) m.copy(content = finalText, isStreaming = false)
                                        else m
                                    },
                                    isGenerating = false,
                                )
                            }
                        }
                        // Log and show metrics on success
                        if (err == null && tFirstToken > 0 && tokenCount > 0) {
                            val metrics = InferenceMetrics(
                                promptId       = "chat",
                                quantVariant   = _uiState.value.currentVariant,
                                contextLength  = contextLength,
                                outputLength   = tokenCount,
                                tRequestStart  = tStart,
                                tFirstToken    = tFirstToken,
                                tLastToken     = tEnd,
                                inputTokens    = estimateTokens(text),
                                outputTokens   = tokenCount,
                                peakRssMb      = getPeakRssMb(),
                            )
                            withContext(Dispatchers.Main) {
                                _uiState.update { it.copy(liveMetrics = toLiveMetrics(metrics)) }
                            }
                            logger.logSuccess(metrics, "compose-v2", trialCounter++, isWarmup = false)
                        }
                    }
                    .collect { token ->
                        if (tFirstToken < 0 && token.isNotEmpty()) tFirstToken = nowSeconds()
                        tokenCount++
                        buffer.append(token)
                        val snapshot = buffer.toString()
                        withContext(Dispatchers.Main) {
                            _uiState.update { state ->
                                state.copy(messages = state.messages.map { m ->
                                    if (m.id == asstId) m.copy(content = snapshot) else m
                                })
                            }
                        }
                    }
            } catch (e: CancellationException) {
                // User tapped stop — finalise with [stopped] marker
                val stoppedText = buffer.toString() + if (buffer.isNotEmpty()) " [stopped]" else "[stopped]"
                withContext(Dispatchers.Main) {
                    _uiState.update { state ->
                        state.copy(
                            messages = state.messages.map { m ->
                                if (m.id == asstId) m.copy(content = stoppedText, isStreaming = false)
                                else m
                            },
                            isGenerating = false,
                        )
                    }
                }
            } catch (e: Exception) {
                withContext(Dispatchers.Main) {
                    _uiState.update { state ->
                        state.copy(
                            messages = state.messages.map { m ->
                                if (m.id == asstId) m.copy(content = "[Error: ${e.message}]", isStreaming = false)
                                else m
                            },
                            isGenerating  = false,
                            errorMessage  = e.message,
                        )
                    }
                }
            }
        }
    }

    fun stopGeneration() { generationJob?.cancel() }

    fun clearConversation() {
        _uiState.update {
            ChatUiState(
                currentVariant = it.currentVariant,
                isModelLoaded  = it.isModelLoaded,
                modelName      = it.modelName,
            )
        }
    }

    fun dismissError() { _uiState.update { it.copy(errorMessage = null) } }

    // ── Utilities ─────────────────────────────────────────────────────────────

    private fun appendSystemMessage(text: String) {
        _uiState.update { it.copy(messages = it.messages + ChatMessage(role = "system", content = text)) }
    }

    private fun nowSeconds(): Double = System.currentTimeMillis() / 1000.0

    private fun estimateTokens(text: String): Int = (text.length / 4).coerceAtLeast(1)

    private fun getPeakRssMb(): Double? = try {
        val mi = android.os.Debug.MemoryInfo()
        android.os.Debug.getMemoryInfo(mi)
        mi.totalPss / 1024.0
    } catch (e: Exception) { null }

    private fun toLiveMetrics(m: InferenceMetrics) = LiveMetrics(
        ttftS      = m.ttftS,
        prefillTps = m.prefillTps,
        decodeTps  = m.decodeTps,
        e2eS       = m.e2eS,
        peakRssMb  = m.peakRssMb,
    )

    override fun onCleared() {
        super.onCleared()
        // Engine singleton is long-lived; do NOT call destroy() here
    }
}
