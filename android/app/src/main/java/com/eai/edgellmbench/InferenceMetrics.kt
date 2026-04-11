package com.eai.edgellmbench

/**
 * Holds timing + throughput metrics for a single inference run.
 * Mirrors the PRD metric definitions exactly.
 */
data class InferenceMetrics(
    val promptId: String,
    val quantVariant: String,
    val contextLength: Int,
    val outputLength: Int,

    // Raw wall-clock timestamps (seconds since epoch)
    val tRequestStart: Double,
    val tFirstToken: Double,
    val tLastToken: Double,

    // Token counts
    val inputTokens: Int,
    val outputTokens: Int,

    // Resource
    val peakRssMb: Double? = null,
    val batteryStartPct: Float? = null,
    val batteryEndPct: Float? = null,
) {
    // Derived metrics — all match PRD definitions
    val ttftS: Double get() = tFirstToken - tRequestStart
    val prefillS: Double get() = tFirstToken - tRequestStart
    val genS: Double get() = tLastToken - tFirstToken
    val e2eS: Double get() = tLastToken - tRequestStart
    val prefillTps: Double get() = if (prefillS > 0) inputTokens.toDouble() / prefillS else 0.0
    val decodeTps: Double get() = if (genS > 0) outputTokens.toDouble() / genS else 0.0
    val genOverPrefill: Double get() = if (prefillS > 0) genS / prefillS else 0.0
    val prefillFrac: Double get() = if (e2eS > 0) prefillS / e2eS else 0.0
    val genFrac: Double get() = if (e2eS > 0) genS / e2eS else 0.0
    val batteryDropPct: Float? get() = if (batteryStartPct != null && batteryEndPct != null)
        maxOf(0f, batteryStartPct - batteryEndPct) else null
}
