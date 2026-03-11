package com.eai.edgellmbench.data

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.floatPreferencesKey
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore

// ---------------------------------------------------------------------------
// Shared DataStore extension — ONE instance per process (by delegate contract)
// Import this in any ViewModel that needs to read or write inference settings.
// ---------------------------------------------------------------------------

val Context.settingsDataStore: DataStore<Preferences>
    by preferencesDataStore(name = "inference_settings")

// ---------------------------------------------------------------------------
// DataStore preference keys shared across SettingsViewModel, BenchmarkViewModel
// ---------------------------------------------------------------------------

object SettingsKeys {
    val THREAD_COUNT      = intPreferencesKey("thread_count")
    val CONTEXT_LENGTH    = intPreferencesKey("context_length")
    val OUTPUT_LENGTH     = intPreferencesKey("output_length")
    val TEMPERATURE       = floatPreferencesKey("temperature")
    val SEED              = intPreferencesKey("seed")
    val WARMUP_RUNS       = intPreferencesKey("warmup_runs")
    val BENCH_RUNS        = intPreferencesKey("bench_runs")
    // Persisted last-used model for cold-start auto-load
    val LAST_MODEL_PATH    = stringPreferencesKey("last_model_path")
    val LAST_MODEL_VARIANT = stringPreferencesKey("last_model_variant")
    // Dark / light mode override
    val DARK_MODE_USE_SYSTEM = booleanPreferencesKey("dark_mode_use_system") // true = follow system
    val DARK_MODE_IS_DARK    = booleanPreferencesKey("dark_mode_is_dark")    // only used when use_system=false
}

// ---------------------------------------------------------------------------
// Default values (single source of truth)
// ---------------------------------------------------------------------------

object SettingsDefaults {
    const val THREAD_COUNT        = 4
    const val CONTEXT_LENGTH      = 512
    const val OUTPUT_LENGTH       = 128
    const val TEMPERATURE         = 0.7f
    const val SEED                = 42
    const val WARMUP_RUNS         = 1
    const val BENCH_RUNS          = 3
    const val DARK_MODE_USE_SYSTEM = true
    const val DARK_MODE_IS_DARK    = true
}
