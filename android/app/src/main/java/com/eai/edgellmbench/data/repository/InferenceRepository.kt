package com.eai.edgellmbench.data.repository

import android.content.Context
import com.arm.aichat.AiChat
import com.arm.aichat.InferenceEngine
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Shared singleton state for which GGUF model is currently loaded.
 * All ViewModels observe [modelState] and call [getEngine] for inference.
 *
 * [AiChat.getInferenceEngine] is itself a singleton so any ViewModel that
 * calls it gets the same underlying InferenceEngineImpl instance.
 */
object InferenceRepository {

    data class ModelState(
        val variant: String = "Q4_K_M",
        val isLoaded: Boolean = false,
        val modelPath: String? = null,
        val isLoading: Boolean = false,
    )

    private val _modelState = MutableStateFlow(ModelState())
    val modelState: StateFlow<ModelState> = _modelState.asStateFlow()

    /** Call after a successful [InferenceEngine.loadModel]. */
    fun markLoaded(variant: String, path: String) {
        _modelState.value = ModelState(variant = variant, isLoaded = true, modelPath = path, isLoading = false)
    }

    /** Call while model is being loaded from disk. */
    fun markLoading(variant: String) {
        _modelState.value = _modelState.value.copy(isLoading = true, variant = variant)
    }

    /** Call when the current model is unloaded or a new variant is selected. */
    fun markUnloaded(nextVariant: String = _modelState.value.variant) {
        _modelState.value = ModelState(variant = nextVariant)
    }

    /** Returns the shared InferenceEngine singleton. */
    fun getEngine(context: Context): InferenceEngine =
        AiChat.getInferenceEngine(context.applicationContext)
}
