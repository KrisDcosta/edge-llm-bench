package com.eai.edgellmbench.ui.models

import android.app.Application
import android.net.Uri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.eai.edgellmbench.data.repository.InferenceRepository
import com.eai.edgellmbench.data.repository.ModelRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

data class ModelManagerUiState(
    val activeVariant: String = "Q4_K_M",
    val isModelLoaded: Boolean = false,
    val isLoading: Boolean = false,
    val errorMessage: String? = null,
    /** Variants found in /data/local/tmp/ (pushed by benchmark pipeline) */
    val deviceModels: Set<String> = emptySet(),
)

class ModelManagerViewModel(application: Application) : AndroidViewModel(application) {

    private val _uiState = MutableStateFlow(ModelManagerUiState())
    val uiState: StateFlow<ModelManagerUiState> = _uiState.asStateFlow()

    init {
        // Mirror the shared model state
        viewModelScope.launch {
            InferenceRepository.modelState.collect { ms ->
                _uiState.update {
                    it.copy(
                        activeVariant = ms.variant,
                        isModelLoaded = ms.isLoaded,
                        isLoading     = ms.isLoading,
                    )
                }
            }
        }
        // Scan /data/local/tmp/ for already-pushed models
        refreshDeviceModels()
    }

    /** Re-scans /data/local/tmp/ — call after pushing new models. */
    fun refreshDeviceModels() {
        viewModelScope.launch {
            val found = withContext(Dispatchers.IO) {
                ModelRepository.discoverDeviceModels().toSet()
            }
            _uiState.update { it.copy(deviceModels = found) }
        }
    }

    /**
     * Load a model directly from /data/local/tmp/ (no copy needed).
     * This is the preferred path when models were pushed via the benchmark
     * pipeline (push_models_to_device.sh).
     */
    fun loadFromDevicePath(variant: String) {
        val path = ModelRepository.devicePathForVariant(variant)
        viewModelScope.launch {
            _uiState.update { it.copy(errorMessage = null) }
            try {
                ModelRepository.loadFromPath(getApplication(), path, variant)
            } catch (e: OutOfMemoryError) {
                InferenceRepository.markUnloaded()
                _uiState.update { it.copy(errorMessage = "Out of memory! $variant is too large for this device. Try Q8_0 (3.4 GB) instead.") }
            } catch (e: Exception) {
                InferenceRepository.markUnloaded()
                val errorMsg = when {
                    e.message?.contains("cannot load", ignoreCase = true) == true ->
                        "Model file not found or invalid. Push the model first with:\nadb push Llama-3.2-3B-Instruct-$variant.gguf /data/local/tmp/"
                    else -> "Load failed: ${e.message}"
                }
                _uiState.update { it.copy(errorMessage = errorMsg) }
            }
        }
    }

    /** File picker result: copy from URI then load. */
    fun loadFromUri(uri: Uri, variant: String) {
        viewModelScope.launch {
            _uiState.update { it.copy(errorMessage = null) }
            try {
                ModelRepository.loadFromUri(getApplication(), uri, variant)
            } catch (e: OutOfMemoryError) {
                InferenceRepository.markUnloaded()
                _uiState.update { it.copy(errorMessage = "Out of memory! $variant is too large for this device. Try Q8_0 (3.4 GB) instead.") }
            } catch (e: Exception) {
                InferenceRepository.markUnloaded()
                _uiState.update { it.copy(errorMessage = "Load failed: ${e.message}") }
            }
        }
    }

    fun dismissError() { _uiState.update { it.copy(errorMessage = null) } }
}
