package com.eai.edgellmbench.data.repository

import android.content.Context
import android.net.Uri
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileOutputStream

/**
 * Handles GGUF model file management: copying from a content URI to local
 * storage and loading into the inference engine.
 */
object ModelRepository {

    private const val MODEL_DIR = "models"

    /**
     * Copies the GGUF from [uri] to the app's private files directory
     * (skips copy if the same filename already exists), then loads it into
     * the engine and updates [InferenceRepository].
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

        // Load into engine (suspend)
        InferenceRepository.getEngine(context).loadModel(file.absolutePath)

        InferenceRepository.markLoaded(variant, file.absolutePath)
        file.name
    }

    /** Lists all .gguf files previously copied to local storage. */
    fun listLocalModels(context: Context): List<File> {
        val dir = File(context.filesDir, MODEL_DIR)
        return if (dir.exists()) dir.listFiles { f -> f.extension == "gguf" }?.toList() ?: emptyList()
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
