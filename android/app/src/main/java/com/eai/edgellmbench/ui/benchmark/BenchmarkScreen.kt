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
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.eai.edgellmbench.data.db.BenchmarkRunEntity
import com.eai.edgellmbench.ui.settings.SettingsViewModel
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BenchmarkScreen(
    viewModel: BenchmarkViewModel = viewModel(),
    settingsVm: SettingsViewModel = viewModel(),
) {
    val uiState by viewModel.uiState.collectAsState()
    val settingsState by settingsVm.uiState.collectAsState()
    val historyRuns by viewModel.historyRuns.collectAsState()
    val context = LocalContext.current
    val snackbarHostState = remember { SnackbarHostState() }
    var selectedTab by remember { mutableIntStateOf(0) }

    LaunchedEffect(uiState.errorMessage) {
        uiState.errorMessage?.let {
            snackbarHostState.showSnackbar(it, duration = SnackbarDuration.Short)
            viewModel.dismissError()
        }
    }

    // Switch to Run tab when a benchmark starts
    LaunchedEffect(uiState.status) {
        if (uiState.status is BenchmarkStatus.Running) selectedTab = 0
    }

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
                .padding(paddingValues),
        ) {
            // ── Tab row ───────────────────────────────────────────────────────
            TabRow(selectedTabIndex = selectedTab) {
                Tab(
                    selected = selectedTab == 0,
                    onClick  = { selectedTab = 0 },
                    text     = { Text("Run") },
                )
                Tab(
                    selected = selectedTab == 1,
                    onClick  = { selectedTab = 1 },
                    text     = { Text("History (${historyRuns.size})") },
                )
            }

            when (selectedTab) {
                // ── Run tab ───────────────────────────────────────────────────
                0 -> Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(16.dp),
                ) {
                    BenchmarkStatusCard(uiState = uiState, configText = configText)

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

                    if (uiState.status == BenchmarkStatus.Complete && uiState.results.isNotEmpty()) {
                        BenchmarkSummaryCard(results = uiState.results.filter { !it.isWarmup })
                    }

                    if (uiState.results.isNotEmpty()) {
                        HorizontalDivider()
                        Text("Trial Results", style = MaterialTheme.typography.titleSmall)
                        ResultsTable(results = uiState.results)
                    }
                }

                // ── History tab ───────────────────────────────────────────────
                1 -> HistoryList(runs = historyRuns)
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

// ── History list ──────────────────────────────────────────────────────────────

@Composable
private fun HistoryList(runs: List<BenchmarkRunEntity>) {
    if (runs.isEmpty()) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(32.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            Text(
                text = "No benchmark runs yet",
                style = MaterialTheme.typography.titleMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(8.dp))
            Text(
                text = "Run a benchmark on the Run tab to see results here.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        return
    }

    val dateFmt = remember { SimpleDateFormat("MMM d, HH:mm", Locale.getDefault()) }

    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
        contentPadding = PaddingValues(vertical = 12.dp),
    ) {
        items(runs) { run ->
            HistoryRunCard(run = run, dateFmt = dateFmt)
        }
    }
}

@Composable
private fun HistoryRunCard(run: BenchmarkRunEntity, dateFmt: SimpleDateFormat) {
    ElevatedCard(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            // Header row: variant + date
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = run.modelVariant,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary,
                )
                Text(
                    text = dateFmt.format(Date(run.timestamp)),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Spacer(Modifier.height(4.dp))
            // Config row
            Text(
                text = "ctx=${run.contextLength} · ${run.outputLength} tokens · ${run.numTrials} trials",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(8.dp))
            // Stats row
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceEvenly,
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(
                        text = "Decode TPS",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Text(
                        text = "%.2f".format(run.meanDecodeTps),
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold,
                        fontFamily = FontFamily.Monospace,
                    )
                    Text(
                        text = "±%.2f  [%.1f–%.1f]".format(run.stdDecodeTps, run.minDecodeTps, run.maxDecodeTps),
                        style = MaterialTheme.typography.bodySmall,
                        fontFamily = FontFamily.Monospace,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(
                        text = "TTFT",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Text(
                        text = "%.2fs".format(run.meanTtftS),
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold,
                        fontFamily = FontFamily.Monospace,
                    )
                }
            }
        }
    }
}

@Composable
private fun ResultsTable(results: List<TrialResult>) {
    // Use a regular Column (not LazyColumn) to avoid unbounded-height crash when
    // this composable is nested inside a Column with Arrangement.spacedBy().
    // Trial count is bounded (warmup + bench runs ≤ ~20 rows), so no scrolling needed.
    Column(
        modifier = Modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        // Header row
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(vertical = 4.dp),
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

        // Data rows
        results.filter { !it.isWarmup }.forEach { r ->
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
