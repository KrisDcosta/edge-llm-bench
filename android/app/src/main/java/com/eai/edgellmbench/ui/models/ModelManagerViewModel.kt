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
            } catch (e: Exception) {
                InferenceRepository.markUnloaded()
                _uiState.update { it.copy(errorMessage = "Load failed: ${e.message}") }
            }
        }
    }

    /** File picker result: copy from URI then load. */
    fun loadFromUri(uri: Uri, variant: String) {
        viewModelScope.launch {
            _uiState.update { it.copy(errorMessage = null) }
            try {
                ModelRepository.loadFromUri(getApplication(), uri, variant)
            } catch (e: Exception) {
                InferenceRepository.markUnloaded()
                _uiState.update { it.copy(errorMessage = "Load failed: ${e.message}") }
            }
        }
    }

    fun dismissError() { _uiState.update { it.copy(errorMessage = null) } }
}
