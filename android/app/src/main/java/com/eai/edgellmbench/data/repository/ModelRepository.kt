package com.eai.edgellmbench.data.repository

import android.content.Context
import android.net.Uri
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileOutputStream

/**
 * Handles GGUF model file management: discovering models already on the device
 * (pushed by the benchmark pipeline to /data/local/tmp/), loading from an
 * absolute path, or copying from a content URI picked via file picker.
 */
object ModelRepository {

    private const val MODEL_DIR = "models"

    /**
     * The directory where the benchmark pipeline (push_models_to_device.sh)
     * places GGUF files.  /data/local/tmp/ is world-readable on Android ≥ 5,
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
     */
    suspend fun loadFromPath(
        context: Context,
        path: String,
        variant: String,
    ): String = withContext(Dispatchers.IO) {
        InferenceRepository.markLoading(variant)
        InferenceRepository.getEngine(context).loadModel(path)
        InferenceRepository.markLoaded(variant, path)
        File(path).name
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

        val file = copyUriToLocal(context, uri)
        InferenceRepository.getEngine(context).loadModel(file.absolutePath)
        InferenceRepository.markLoaded(variant, file.absolutePath)
        file.name
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
