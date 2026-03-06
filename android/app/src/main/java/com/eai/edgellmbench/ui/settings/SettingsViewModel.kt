package com.eai.edgellmbench.ui.settings

import android.app.Application
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.floatPreferencesKey
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

// ── DataStore extension (one per process) ─────────────────────────────────────

private val android.content.Context.settingsDataStore: DataStore<Preferences>
        by preferencesDataStore(name = "inference_settings")

// ── Keys ─────────────────────────────────────────────────────────────────────

private object Keys {
    val THREAD_COUNT    = intPreferencesKey("thread_count")
    val CONTEXT_LENGTH  = intPreferencesKey("context_length")
    val OUTPUT_LENGTH   = intPreferencesKey("output_length")
    val TEMPERATURE     = floatPreferencesKey("temperature")
    val SEED            = intPreferencesKey("seed")
}

// ── UI state ─────────────────────────────────────────────────────────────────

data class SettingsUiState(
    val threadCount:   Int   = 4,
    val contextLength: Int   = 512,
    val outputLength:  Int   = 128,
    val temperature:   Float = 0.7f,
    val seed:          Int   = 42,
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
                        threadCount   = prefs[Keys.THREAD_COUNT]   ?: 4,
                        contextLength = prefs[Keys.CONTEXT_LENGTH]  ?: 512,
                        outputLength  = prefs[Keys.OUTPUT_LENGTH]   ?: 128,
                        temperature   = prefs[Keys.TEMPERATURE]     ?: 0.7f,
                        seed          = prefs[Keys.SEED]            ?: 42,
                    )
                }
            }
        }
    }

    fun setThreadCount(value: Int) = persist { it[Keys.THREAD_COUNT] = value.coerceIn(1, 8) }
    fun setContextLength(value: Int) = persist { it[Keys.CONTEXT_LENGTH] = value }
    fun setOutputLength(value: Int) = persist { it[Keys.OUTPUT_LENGTH] = value }
    fun setTemperature(value: Float) = persist { it[Keys.TEMPERATURE] = value.coerceIn(0f, 1f) }
    fun setSeed(value: Int) = persist { it[Keys.SEED] = value }

    private fun persist(block: suspend (MutablePreferences) -> Unit) {
        viewModelScope.launch { dataStore.edit { block(it) } }
    }
}

// Type alias to avoid the fully-qualified Preferences.Editor import
private typealias MutablePreferences = androidx.datastore.preferences.core.MutablePreferences
