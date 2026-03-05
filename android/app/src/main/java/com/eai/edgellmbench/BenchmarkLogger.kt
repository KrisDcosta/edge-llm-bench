package com.eai.edgellmbench

import android.content.Context
import android.os.Build
import org.json.JSONObject
import java.io.File
import java.time.Instant
import java.util.UUID

/**
 * Writes schema-valid JSONL records to the app's files directory.
 * Schema: schemas/run.schema.json (record_version 1.0)
 */
class BenchmarkLogger(private val context: Context) {

    private val runId: String = "ui-${Instant.now().toString().replace(":", "").take(15)}"
    private val outputFile: File by lazy {
        File(context.filesDir, "results/$runId.jsonl").also {
            it.parentFile?.mkdirs()
        }
    }

    /** Write one schema-valid JSONL record for a successful trial. */
    fun logSuccess(
        metrics: InferenceMetrics,
        llamaVersion: String,
        trialIndex: Int,
        isWarmup: Boolean,
    ) {
        val record = buildRecord(
            status = "success",
            metrics = metrics,
            llamaVersion = llamaVersion,
            trialIndex = trialIndex,
            isWarmup = isWarmup,
            failure = null,
        )
        append(record)
    }

    /** Write one schema-valid JSONL record for a failed trial. */
    fun logFailure(
        quantVariant: String,
        contextLength: Int,
        promptId: String,
        llamaVersion: String,
        trialIndex: Int,
        isWarmup: Boolean,
        code: String,
        message: String,
    ) {
        val now = System.currentTimeMillis() / 1000.0
        val emptyMetrics = InferenceMetrics(
            promptId = promptId,
            quantVariant = quantVariant,
            contextLength = contextLength,
            outputLength = 0,
            tRequestStart = now,
            tFirstToken = now,
            tLastToken = now,
            inputTokens = 0,
            outputTokens = 0,
        )
        val failure = JSONObject().apply {
            put("code", code)
            put("stage", "inference")
            put("message", message.take(500))
            put("retryable", false)
        }
        val record = buildRecord(
            status = "failed",
            metrics = emptyMetrics,
            llamaVersion = llamaVersion,
            trialIndex = trialIndex,
            isWarmup = isWarmup,
            failure = failure,
        )
        append(record)
    }

    private fun buildRecord(
        status: String,
        metrics: InferenceMetrics,
        llamaVersion: String,
        trialIndex: Int,
        isWarmup: Boolean,
        failure: JSONObject?,
    ): JSONObject {
        val isSuccess = status == "success"
        return JSONObject().apply {
            put("record_version", "1.0")
            put("run_id", "${runId}-t${trialIndex}")
            put("status", status)

            put("device", JSONObject().apply {
                put("manufacturer", Build.MANUFACTURER)
                put("model", "${Build.MANUFACTURER} ${Build.MODEL}")
                put("android_version", Build.VERSION.RELEASE)
                put("build_fingerprint", Build.FINGERPRINT)
            })

            put("build", JSONObject().apply {
                put("framework", "llama.cpp")
                put("framework_version", llamaVersion)
                put("gguf_variant", metrics.quantVariant)
            })

            put("model", JSONObject().apply {
                put("name", "Llama-3.2-3B-Instruct")
                put("artifact_hash", JSONObject.NULL)  // not tracked in UI mode
                put("quant_bits", quantVariantToBits(metrics.quantVariant))
            })

            put("trial", JSONObject().apply {
                put("prompt_id", metrics.promptId)
                put("context_length", metrics.contextLength)
                put("output_length", metrics.outputLength)
                put("trial_index", trialIndex)
                put("is_warmup", isWarmup)
            })

            put("timing_s", JSONObject().apply {
                put("t_request_start", if (isSuccess) metrics.tRequestStart else JSONObject.NULL)
                put("t_model_forward_start", if (isSuccess) metrics.tRequestStart else JSONObject.NULL)
                put("t_first_token", if (isSuccess) metrics.tFirstToken else JSONObject.NULL)
                put("t_last_token", if (isSuccess) metrics.tLastToken else JSONObject.NULL)
            })

            put("tokens", JSONObject().apply {
                put("input_tokens", if (isSuccess) metrics.inputTokens else JSONObject.NULL)
                put("output_tokens", if (isSuccess) metrics.outputTokens else JSONObject.NULL)
            })

            put("metrics", JSONObject().apply {
                put("ttft_s", if (isSuccess) metrics.ttftS.round4() else JSONObject.NULL)
                put("prefill_s", if (isSuccess) metrics.prefillS.round4() else JSONObject.NULL)
                put("prefill_tps", if (isSuccess) metrics.prefillTps.round2() else JSONObject.NULL)
                put("gen_s", if (isSuccess) metrics.genS.round4() else JSONObject.NULL)
                put("decode_tps", if (isSuccess) metrics.decodeTps.round2() else JSONObject.NULL)
                put("e2e_s", if (isSuccess) metrics.e2eS.round4() else JSONObject.NULL)
                put("gen_over_prefill", if (isSuccess) metrics.genOverPrefill.round4() else JSONObject.NULL)
                put("prefill_frac", if (isSuccess) metrics.prefillFrac.round4() else JSONObject.NULL)
                put("gen_frac", if (isSuccess) metrics.genFrac.round4() else JSONObject.NULL)
            })

            put("resources", JSONObject().apply {
                put("peak_rss_mb", metrics.peakRssMb ?: JSONObject.NULL)
                put("battery_start_pct", metrics.batteryStartPct ?: JSONObject.NULL)
                put("battery_end_pct", metrics.batteryEndPct ?: JSONObject.NULL)
                put("battery_drop_pct", metrics.batteryDropPct ?: JSONObject.NULL)
                put("battery_drop_per_1k_tokens", JSONObject.NULL)
                put("temperature_c", JSONObject.NULL)
            })

            put("failure", failure ?: JSONObject.NULL)
        }
    }

    private fun append(record: JSONObject) {
        outputFile.appendText(record.toString() + "\n")
    }

    fun getOutputPath(): String = outputFile.absolutePath

    private fun quantVariantToBits(variant: String): Int = when {
        variant.startsWith("Q2") -> 2
        variant.startsWith("Q3") -> 3
        variant.startsWith("Q4") -> 4
        variant.startsWith("Q6") -> 6
        variant.startsWith("Q8") -> 8
        variant.startsWith("F16") -> 16
        else -> 4
    }

    private fun Double.round4() = Math.round(this * 10000.0) / 10000.0
    private fun Double.round2() = Math.round(this * 100.0) / 100.0
}
