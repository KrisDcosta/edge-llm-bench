package com.eai.edgellmbench.ui.settings

import android.app.Application
import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.eai.edgellmbench.data.SettingsDefaults
import com.eai.edgellmbench.data.SettingsKeys
import com.eai.edgellmbench.data.settingsDataStore
import com.eai.edgellmbench.data.repository.InferenceRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

// ── UI state ─────────────────────────────────────────────────────────────────

data class SettingsUiState(
    val threadCount:       Int     = SettingsDefaults.THREAD_COUNT,
    val contextLength:     Int     = SettingsDefaults.CONTEXT_LENGTH,
    val outputLength:      Int     = SettingsDefaults.OUTPUT_LENGTH,
    val temperature:       Float   = SettingsDefaults.TEMPERATURE,
    val seed:              Int     = SettingsDefaults.SEED,
    val warmupRuns:        Int     = SettingsDefaults.WARMUP_RUNS,
    val benchRuns:         Int     = SettingsDefaults.BENCH_RUNS,
    val isApplying:        Boolean = false,
    val applyResult:       String? = null,   // null = idle; "" = success; "Error: …" = failure
    val darkModeUseSystem: Boolean = SettingsDefaults.DARK_MODE_USE_SYSTEM,
    val darkModeIsDark:    Boolean = SettingsDefaults.DARK_MODE_IS_DARK,
)

// ── ViewModel ─────────────────────────────────────────────────────────────────

class SettingsViewModel(application: Application) : AndroidViewModel(application) {

    private val dataStore = application.settingsDataStore

    private val _uiState = MutableStateFlow(SettingsUiState())
    val uiState: StateFlow<SettingsUiState> = _uiState.asStateFlow()

    init {
        viewModelScope.launch {
            dataStore.data.collect { prefs ->
                _uiState.update { _ ->
                    SettingsUiState(
                        threadCount       = prefs[SettingsKeys.THREAD_COUNT]        ?: SettingsDefaults.THREAD_COUNT,
                        contextLength     = prefs[SettingsKeys.CONTEXT_LENGTH]      ?: SettingsDefaults.CONTEXT_LENGTH,
                        outputLength      = prefs[SettingsKeys.OUTPUT_LENGTH]       ?: SettingsDefaults.OUTPUT_LENGTH,
                        temperature       = prefs[SettingsKeys.TEMPERATURE]         ?: SettingsDefaults.TEMPERATURE,
                        seed              = prefs[SettingsKeys.SEED]                ?: SettingsDefaults.SEED,
                        warmupRuns        = prefs[SettingsKeys.WARMUP_RUNS]         ?: SettingsDefaults.WARMUP_RUNS,
                        benchRuns         = prefs[SettingsKeys.BENCH_RUNS]          ?: SettingsDefaults.BENCH_RUNS,
                        darkModeUseSystem = prefs[SettingsKeys.DARK_MODE_USE_SYSTEM] ?: SettingsDefaults.DARK_MODE_USE_SYSTEM,
                        darkModeIsDark    = prefs[SettingsKeys.DARK_MODE_IS_DARK]    ?: SettingsDefaults.DARK_MODE_IS_DARK,
                    )
                }
            }
        }
    }

    fun setThreadCount(value: Int)   = persist { it[SettingsKeys.THREAD_COUNT]   = value.coerceIn(1, 8) }
    fun setContextLength(value: Int) = persist { it[SettingsKeys.CONTEXT_LENGTH] = value }
    fun setOutputLength(value: Int)  = persist { it[SettingsKeys.OUTPUT_LENGTH]  = value }
    fun setTemperature(value: Float) = persist { it[SettingsKeys.TEMPERATURE]    = value.coerceIn(0f, 1f) }
    fun setSeed(value: Int)          = persist { it[SettingsKeys.SEED]           = value }
    fun setWarmupRuns(value: Int)           = persist { it[SettingsKeys.WARMUP_RUNS]         = value.coerceIn(0, 2) }
    fun setBenchRuns(value: Int)            = persist { it[SettingsKeys.BENCH_RUNS]           = value }
    fun setDarkModeUseSystem(value: Boolean) = persist { it[SettingsKeys.DARK_MODE_USE_SYSTEM] = value }
    fun setDarkModeIsDark(value: Boolean)    = persist { it[SettingsKeys.DARK_MODE_IS_DARK]    = value }

    /**
     * Reconfigures the live inference engine with current settings (no model reload needed).
     * Updates thread count, temperature and seed immediately; resets KV cache.
     */
    fun applySettings(context: Context) {
        viewModelScope.launch {
            _uiState.update { it.copy(isApplying = true, applyResult = null) }
            try {
                val engine = InferenceRepository.getEngine(context)
                val s = _uiState.value
                engine.configure(
                    contextLength = s.contextLength,
                    threadCount   = s.threadCount,
                    temperature   = s.temperature,
                    seed          = s.seed.toLong(),
                )
                _uiState.update { it.copy(isApplying = false, applyResult = "Applied!") }
            } catch (e: Exception) {
                _uiState.update { it.copy(isApplying = false, applyResult = "Error: ${e.message}") }
            }
        }
    }

    private fun persist(block: suspend (MutablePreferences) -> Unit) {
        viewModelScope.launch { dataStore.edit { block(it) } }
    }
}

// Type alias to avoid the fully-qualified Preferences.Editor import
private typealias MutablePreferences = androidx.datastore.preferences.core.MutablePreferences
