package com.eai.edgellmbench.data.repository

import android.content.Context
import android.net.Uri
import android.util.Log
import androidx.datastore.preferences.core.edit
import com.arm.aichat.InferenceEngine
import com.eai.edgellmbench.data.SettingsDefaults
import com.eai.edgellmbench.data.SettingsKeys
import com.eai.edgellmbench.data.settingsDataStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileOutputStream

/**
 * Handles GGUF model file management: discovering models already on the device
 * (pushed by the benchmark pipeline to /data/local/tmp/), loading from an
 * absolute path, or copying from a content URI picked via file picker.
 */
object ModelRepository {

    private const val TAG = "ModelRepository"
    private const val MODEL_DIR = "models"

    /**
     * The directory where the benchmark pipeline (push_models_to_device.sh)
     * places GGUF files.  /data/local/tmp/ is world-readable on Android,
     * so a debug APK can open files there directly without copying.
     */
    private const val DEVICE_TMP = "/data/local/tmp"

    /** Expected filename for a given variant on the device. */
    fun devicePathForVariant(variant: String) =
        "$DEVICE_TMP/Llama-3.2-3B-Instruct-$variant.gguf"

    /**
     * Checks which known variants are already present in /data/local/tmp/.
     * Returns the list of variant names that have a readable .gguf file there.
     */
    fun discoverDeviceModels(): List<String> =
        knownVariants.map { it.name }.filter { v ->
            try { File(devicePathForVariant(v)).canRead() } catch (_: Exception) { false }
        }

    /**
     * Loads a model directly from an absolute path (e.g. /data/local/tmp/).
     * No copy is needed — the engine opens the file in-place.
     *
     * Handles engine state automatically:
     *  - Initialized  → loadModel() directly (happy path)
     *  - ModelReady   → cleanUp() (unloads previous model) then loadModel()
     *  - Error        → cleanUp() (resets state) then loadModel()
     */
    suspend fun loadFromPath(
        context: Context,
        path: String,
        variant: String,
    ): String = withContext(Dispatchers.IO) {
        InferenceRepository.markLoading(variant)
        val engine = InferenceRepository.getEngine(context)
        resetEngineIfNeeded(engine)
        engine.loadModel(path)
        applyCurrentSettings(context, engine)
        persistLastModel(context, variant, path)
        InferenceRepository.markLoaded(variant, path)
        File(path).name
    }

    /**
     * Attempts to restore the previously loaded model on cold start.
     * Silently no-ops if no prior model is recorded, the file no longer
     * exists, or any error occurs during load.
     *
     * @return the model filename if auto-load succeeded, null otherwise
     */
    suspend fun tryAutoLoad(context: Context): String? = withContext(Dispatchers.IO) {
        try {
            val prefs   = context.settingsDataStore.data.first()
            val path    = prefs[SettingsKeys.LAST_MODEL_PATH]    ?: return@withContext null
            val variant = prefs[SettingsKeys.LAST_MODEL_VARIANT] ?: return@withContext null
            if (!File(path).canRead()) {
                Log.i(TAG, "tryAutoLoad: previous model not readable at $path — skipping")
                return@withContext null
            }
            Log.i(TAG, "tryAutoLoad: restoring $variant from $path")
            loadFromPath(context, path, variant)
        } catch (e: Exception) {
            Log.w(TAG, "tryAutoLoad: failed — ${e.message}")
            null
        }
    }

    /**
     * Copies the GGUF from [uri] (SAF file picker) to the app's private files
     * directory, then loads it into the engine.
     * Skips copy if a file with the same name already exists locally.
     *
     * @return the local model file name on success
     * @throws Exception on IO or engine error
     */
    suspend fun loadFromUri(
        context: Context,
        uri: Uri,
        variant: String,
    ): String = withContext(Dispatchers.IO) {
        InferenceRepository.markLoading(variant)
        val engine = InferenceRepository.getEngine(context)
        resetEngineIfNeeded(engine)
        val file = copyUriToLocal(context, uri)
        engine.loadModel(file.absolutePath)
        applyCurrentSettings(context, engine)
        persistLastModel(context, variant, file.absolutePath)
        InferenceRepository.markLoaded(variant, file.absolutePath)
        file.name
    }

    /**
     * Persists the variant + path of the most recently loaded model to DataStore
     * so it can be restored automatically on the next cold start.
     */
    private suspend fun persistLastModel(context: Context, variant: String, path: String) {
        try {
            context.settingsDataStore.edit { prefs ->
                prefs[SettingsKeys.LAST_MODEL_PATH]    = path
                prefs[SettingsKeys.LAST_MODEL_VARIANT] = variant
            }
        } catch (e: Exception) {
            Log.w(TAG, "persistLastModel: failed — ${e.message}")
        }
    }

    /**
     * Reads current inference settings from DataStore and applies them to the engine
     * via configure(). Non-fatal — logs a warning and continues with default params if it fails.
     */
    private suspend fun applyCurrentSettings(context: Context, engine: InferenceEngine) {
        try {
            val prefs = context.settingsDataStore.data.first()
            engine.configure(
                contextLength = prefs[SettingsKeys.CONTEXT_LENGTH] ?: SettingsDefaults.CONTEXT_LENGTH,
                threadCount   = prefs[SettingsKeys.THREAD_COUNT]   ?: SettingsDefaults.THREAD_COUNT,
                temperature   = prefs[SettingsKeys.TEMPERATURE]    ?: SettingsDefaults.TEMPERATURE,
                seed          = (prefs[SettingsKeys.SEED]          ?: SettingsDefaults.SEED).toLong(),
            )
        } catch (e: Exception) {
            Log.w(TAG, "applyCurrentSettings: non-fatal failure — ${e.message}")
        }
    }

    /**
     * If the engine is in Error or ModelReady state, call cleanUp() to reset
     * it back to Initialized before attempting a new loadModel().
     *
     * loadModel() requires state == Initialized; calling it in any other state
     * throws "Cannot load model in <State>!".
     */
    private fun resetEngineIfNeeded(engine: InferenceEngine) {
        val state = engine.state.value
        when (state) {
            is InferenceEngine.State.Error -> {
                Log.w(TAG, "Engine in Error state — resetting via cleanUp() before reload")
                engine.cleanUp()
            }
            is InferenceEngine.State.ModelReady -> {
                Log.i(TAG, "Engine has a model loaded — unloading via cleanUp() before reload")
                engine.cleanUp()
            }
            else -> {
                Log.d(TAG, "Engine state: ${state.javaClass.simpleName} — proceeding directly")
            }
        }
    }

    /** Lists all .gguf files previously copied to local storage. */
    fun listLocalModels(context: Context): List<File> {
        val dir = File(context.filesDir, MODEL_DIR)
        return if (dir.exists()) dir.listFiles { f -> f.extension == "gguf" }?.toList()
            ?: emptyList()
        else emptyList()
    }

    private suspend fun copyUriToLocal(context: Context, uri: Uri): File =
        withContext(Dispatchers.IO) {
            val dir = File(context.filesDir, MODEL_DIR).also { it.mkdirs() }
            val filename = uri.lastPathSegment?.substringAfterLast('/')
                ?: "model_${System.currentTimeMillis()}.gguf"
            val dest = File(dir, filename)
            if (!dest.exists()) {
                context.contentResolver.openInputStream(uri)?.use { ins ->
                    FileOutputStream(dest).use { ins.copyTo(it) }
                }
            }
            dest
        }

    /** Variant metadata used by ModelManagerScreen. */
    data class VariantInfo(
        val name: String,
        val bits: Int,
        val sizeGb: Float,
        val note: String = "",
    )

    val knownVariants = listOf(
        VariantInfo("Q2_K",   2, 1.3f, "Smallest — fastest decode"),
        VariantInfo("Q3_K_M", 3, 1.6f),
        VariantInfo("Q4_K_M", 4, 2.0f, "Recommended — Pareto optimal"),
        VariantInfo("Q6_K",   6, 2.7f),
        VariantInfo("Q8_0",   8, 3.4f, "High quality — 6 GB tight"),
        VariantInfo("F16",   16, 6.4f, "Expected OOM on 6 GB device"),
    )
}
