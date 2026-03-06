package com.eai.edgellmbench.ui.models

import android.app.Application
import android.net.Uri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.eai.edgellmbench.data.repository.InferenceRepository
import com.eai.edgellmbench.data.repository.ModelRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class ModelManagerUiState(
    val activeVariant: String = "Q4_K_M",
    val isModelLoaded: Boolean = false,
    val isLoading: Boolean = false,
    val errorMessage: String? = null,
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
    }

    /** Open file picker result: copy + load the selected GGUF. */
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
