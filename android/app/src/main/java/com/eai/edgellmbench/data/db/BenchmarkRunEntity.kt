package com.eai.edgellmbench.data.db

import androidx.room.Entity
import androidx.room.PrimaryKey

/**
 * One row = one completed benchmark run (all non-warmup trials aggregated).
 * Written by [BenchmarkViewModel] after a run finishes; displayed in the History tab.
 */
@Entity(tableName = "benchmark_runs")
data class BenchmarkRunEntity(
    /** Unique ID — timestamp-based, matches the JSONL filename prefix. */
    @PrimaryKey val runId: String,
    /** Wall-clock time at which the run completed (epoch millis). */
    val timestamp: Long,
    /** GGUF quantization variant label, e.g. "Q4_K_M". */
    val modelVariant: String,
    /** Context window length used, e.g. 512. */
    val contextLength: Int,
    /** Max output tokens setting. */
    val outputLength: Int,
    /** Number of non-warmup trials that completed. */
    val numTrials: Int,
    /** Mean decode throughput across all trials (tokens/sec). */
    val meanDecodeTps: Double,
    /** Sample standard deviation of decode TPS. */
    val stdDecodeTps: Double,
    /** Minimum decode TPS across trials. */
    val minDecodeTps: Double,
    /** Maximum decode TPS across trials. */
    val maxDecodeTps: Double,
    /** Mean time-to-first-token (seconds). */
    val meanTtftS: Double,
)
