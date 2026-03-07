package com.eai.edgellmbench.ui.benchmark

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Share
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ElevatedButton
import androidx.compose.material3.ElevatedCard
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarDuration
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.eai.edgellmbench.ui.settings.SettingsViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BenchmarkScreen(
    viewModel: BenchmarkViewModel = viewModel(),
    settingsVm: SettingsViewModel = viewModel(),
) {
    val uiState by viewModel.uiState.collectAsState()
    val settingsState by settingsVm.uiState.collectAsState()
    val context = LocalContext.current
    val snackbarHostState = remember { SnackbarHostState() }

    LaunchedEffect(uiState.errorMessage) {
        uiState.errorMessage?.let {
            snackbarHostState.showSnackbar(it, duration = SnackbarDuration.Short)
            viewModel.dismissError()
        }
    }

    // Build the config description string from live settings
    val configText = buildString {
        val warmup = settingsState.warmupRuns
        val bench  = settingsState.benchRuns
        append("$warmup warmup + $bench trial${if (bench != 1) "s" else ""}")
        append(" · ${BENCH_PROMPT_COUNT} prompts")
        append(" · ${settingsState.outputLength} tokens")
        append(" · ctx=${settingsState.contextLength}")
    }

    Scaffold(
        topBar = { TopAppBar(title = { Text("Benchmark") }) },
        snackbarHost = { SnackbarHost(snackbarHostState) },
    ) { paddingValues ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            // Status card — shows live settings
            BenchmarkStatusCard(uiState = uiState, configText = configText)

            // Control buttons
            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                modifier = Modifier.fillMaxWidth(),
            ) {
                when (val status = uiState.status) {
                    is BenchmarkStatus.Running -> {
                        Column(modifier = Modifier.weight(1f)) {
                            LinearProgressIndicator(
                                progress = { status.current.toFloat() / status.total.toFloat() },
                                modifier = Modifier.fillMaxWidth(),
                            )
                            Spacer(Modifier.height(4.dp))
                            Text(
                                text = "${status.phase} (${status.current}/${status.total})",
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        OutlinedButton(
                            onClick = { viewModel.stopBenchmark() },
                            colors = ButtonDefaults.outlinedButtonColors(
                                contentColor = MaterialTheme.colorScheme.error,
                            ),
                        ) {
                            Icon(Icons.Default.Stop, contentDescription = null)
                            Spacer(Modifier.width(4.dp))
                            Text("Stop")
                        }
                    }

                    else -> {
                        Button(
                            onClick = { viewModel.runBenchmark() },
                            modifier = Modifier.weight(1f),
                            enabled = uiState.isModelLoaded,
                        ) {
                            Icon(Icons.Default.PlayArrow, contentDescription = null)
                            Spacer(Modifier.width(4.dp))
                            Text("Run Benchmark")
                        }
                        if (uiState.status == BenchmarkStatus.Complete) {
                            ElevatedButton(onClick = {
                                viewModel.shareLog()?.let { context.startActivity(it) }
                            }) {
                                Icon(Icons.Default.Share, contentDescription = null)
                                Spacer(Modifier.width(4.dp))
                                Text("Export")
                            }
                        }
                    }
                }
            }

            if (!uiState.isModelLoaded) {
                Text(
                    text = "Go to Models tab to load a GGUF model before benchmarking.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            // Post-benchmark summary card (only shown when complete)
            if (uiState.status == BenchmarkStatus.Complete && uiState.results.isNotEmpty()) {
                BenchmarkSummaryCard(results = uiState.results.filter { !it.isWarmup })
            }

            // Results table
            if (uiState.results.isNotEmpty()) {
                HorizontalDivider()
                Text("Trial Results", style = MaterialTheme.typography.titleSmall)
                ResultsTable(results = uiState.results)
            }
        }
    }
}

// Number of benchmark prompts (kept in sync with BenchmarkViewModel)
private const val BENCH_PROMPT_COUNT = 3

@Composable
private fun BenchmarkStatusCard(uiState: BenchmarkUiState, configText: String) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant,
        ),
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text("MODEL", style = MaterialTheme.typography.labelSmall,
                 color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(
                text = if (uiState.isModelLoaded) uiState.activeVariant else "No model loaded",
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold,
                color = if (uiState.isModelLoaded)
                    MaterialTheme.colorScheme.primary
                else
                    MaterialTheme.colorScheme.onSurfaceVariant,
            )
            if (uiState.isModelLoaded) {
                Text(
                    text = "Llama 3.2 3B Instruct · GGUF",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Spacer(Modifier.height(8.dp))
            Text("Suite", style = MaterialTheme.typography.labelSmall,
                 color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(
                text = configText,
                style = MaterialTheme.typography.bodySmall,
            )
            Spacer(Modifier.height(4.dp))
            Text("Metrics: TTFT · Prefill TPS · Decode TPS · Memory",
                 style = MaterialTheme.typography.bodySmall,
                 color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

// ── Post-benchmark summary card ───────────────────────────────────────────────

@Composable
private fun BenchmarkSummaryCard(results: List<TrialResult>) {
    if (results.isEmpty()) return

    val tpsList  = results.map { it.decodeTps }
    val ttftList = results.map { it.ttftS }

    fun List<Double>.safeMean() = if (isEmpty()) 0.0 else sum() / size
    fun List<Double>.safeStd(): Double {
        if (size < 2) return 0.0
        val m = safeMean()
        return Math.sqrt(sumOf { (it - m) * (it - m) } / (size - 1))
    }

    val meanTps  = tpsList.safeMean()
    val stdTps   = tpsList.safeStd()
    val meanTtft = ttftList.safeMean()
    val stdTtft  = ttftList.safeStd()
    val n        = results.size

    ElevatedCard(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                text = "Benchmark Summary",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
                color = MaterialTheme.colorScheme.primary,
            )
            Spacer(Modifier.height(10.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceEvenly,
            ) {
                SummaryMetric(
                    label = "Decode TPS",
                    value = "%.2f".format(meanTps),
                    sub   = "±%.2f  (n=$n)".format(stdTps),
                )
                SummaryMetric(
                    label = "TTFT",
                    value = "%.2fs".format(meanTtft),
                    sub   = "±%.2fs".format(stdTtft),
                )
            }
        }
    }
}

@Composable
private fun SummaryMetric(label: String, value: String, sub: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(
            text = label,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
            text = value,
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.Bold,
            fontFamily = FontFamily.Monospace,
        )
        Text(
            text = sub,
            style = MaterialTheme.typography.bodySmall,
            fontFamily = FontFamily.Monospace,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun ResultsTable(results: List<TrialResult>) {
    LazyColumn(
        verticalArrangement = Arrangement.spacedBy(6.dp),
        contentPadding = PaddingValues(vertical = 4.dp),
    ) {
        // Header row
        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                listOf("Trial", "Prompt", "Decode TPS", "TTFT").forEach { header ->
                    Text(
                        text = header,
                        style = MaterialTheme.typography.labelSmall,
                        fontWeight = FontWeight.SemiBold,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.weight(1f),
                    )
                }
            }
            HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))
        }

        // Data rows
        items(results.filter { !it.isWarmup }) { r ->
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = "#${r.index}",
                    style = MaterialTheme.typography.bodySmall,
                    fontFamily = FontFamily.Monospace,
                    modifier = Modifier.weight(1f),
                )
                Text(
                    text = r.promptId.take(14),
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.weight(1f),
                )
                Text(
                    text = "%.1f".format(r.decodeTps),
                    style = MaterialTheme.typography.bodySmall,
                    fontFamily = FontFamily.Monospace,
                    modifier = Modifier.weight(1f),
                )
                Text(
                    text = "%.2fs".format(r.ttftS),
                    style = MaterialTheme.typography.bodySmall,
                    fontFamily = FontFamily.Monospace,
                    modifier = Modifier.weight(1f),
                )
            }
        }
    }
}
