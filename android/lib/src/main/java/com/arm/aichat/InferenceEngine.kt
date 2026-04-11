package com.arm.aichat

import com.arm.aichat.InferenceEngine.State
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.StateFlow

/**
 * Interface defining the core LLM inference operations.
 */
interface InferenceEngine {
    /**
     * Current state of the inference engine
     */
    val state: StateFlow<State>

    /**
     * Load a model from the given path.
     *
     * @throws UnsupportedArchitectureException if model architecture not supported
     */
    suspend fun loadModel(pathToModel: String)

    /**
     * Sends a system prompt to the loaded model
     */
    suspend fun setSystemPrompt(systemPrompt: String)

    /**
     * Sends a user prompt to the loaded model and returns a Flow of generated tokens.
     */
    fun sendUserPrompt(message: String, predictLength: Int = DEFAULT_PREDICT_LENGTH): Flow<String>

    /**
     * Reconfigures inference parameters without reloading model weights.
     *
     * Recreates the llama context and sampler in-place with the new settings.
     * This resets the conversation KV cache — subsequent inference starts fresh.
     *
     * @param contextLength KV-cache window in tokens (default: 512)
     * @param threadCount   CPU threads; -1 = auto-detect (big + mid cores minus headroom)
     * @param temperature   Sampling temperature 0.0–1.0 (default: 0.3)
     * @param seed          RNG seed for reproducibility; 42 = fixed, 0xFFFFFFFFL = random
     */
    suspend fun configure(
        contextLength: Int   = 512,
        threadCount:   Int   = -1,
        temperature:   Float = 0.3f,
        seed:          Long  = 42L,
    )

    /**
     * Runs a benchmark with the specified parameters.
     */
    suspend fun bench(pp: Int, tg: Int, pl: Int, nr: Int = 1): String

    /**
     * Unloads the currently loaded model.
     */
    fun cleanUp()

    /**
     * Cleans up resources when the engine is no longer needed.
     */
    fun destroy()

    /**
     * States of the inference engine
     */
    sealed class State {
        object Uninitialized : State()
        object Initializing : State()
        object Initialized : State()

        object LoadingModel : State()
        object UnloadingModel : State()
        object ModelReady : State()

        object Benchmarking : State()
        object ProcessingSystemPrompt : State()
        object ProcessingUserPrompt : State()

        object Generating : State()

        data class Error(val exception: Exception) : State()
    }

    companion object {
        const val DEFAULT_PREDICT_LENGTH = 1024
    }
}

val State.isUninterruptible
    get() = this is State.Initializing ||
        this is State.LoadingModel ||
        this is State.UnloadingModel ||
        this is State.Benchmarking ||
        this is State.ProcessingSystemPrompt ||
        this is State.ProcessingUserPrompt

val State.isModelLoaded: Boolean
    get() = this is State.ModelReady ||
        this is State.Benchmarking ||
        this is State.ProcessingSystemPrompt ||
        this is State.ProcessingUserPrompt ||
        this is State.Generating

class UnsupportedArchitectureException : Exception()
