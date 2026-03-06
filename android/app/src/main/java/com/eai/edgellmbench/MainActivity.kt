package com.eai.edgellmbench

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Chat
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Speed
import androidx.compose.material.icons.filled.Storage
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.eai.edgellmbench.ui.benchmark.BenchmarkScreen
import com.eai.edgellmbench.ui.chat.ChatScreen
import com.eai.edgellmbench.ui.models.ModelManagerScreen
import com.eai.edgellmbench.ui.settings.SettingsScreen
import com.eai.edgellmbench.ui.theme.EdgeLLMTheme

// ── Navigation destinations ─────────────────────────────────────────────────

sealed class NavRoute(val route: String, val label: String, val icon: ImageVector) {
    object Chat      : NavRoute("chat",      "Chat",      Icons.Default.Chat)
    object Models    : NavRoute("models",    "Models",    Icons.Default.Storage)
    object Benchmark : NavRoute("benchmark", "Benchmark", Icons.Default.Speed)
    object Settings  : NavRoute("settings",  "Settings",  Icons.Default.Settings)
}

private val bottomNavItems = listOf(
    NavRoute.Chat,
    NavRoute.Models,
    NavRoute.Benchmark,
    NavRoute.Settings,
)

// ── Activity ────────────────────────────────────────────────────────────────

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            EdgeLLMTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    EdgeLLMApp()
                }
            }
        }
    }
}

// ── Root composable ─────────────────────────────────────────────────────────

@Composable
fun EdgeLLMApp() {
    val navController = rememberNavController()

    Scaffold(
        bottomBar = { EdgeLLMBottomBar(navController) },
    ) { innerPadding ->
        NavHost(
            navController = navController,
            startDestination = NavRoute.Chat.route,
            modifier = Modifier.padding(innerPadding),
        ) {
            composable(NavRoute.Chat.route)      { ChatScreen() }
            composable(NavRoute.Models.route)    { ModelManagerScreen() }
            composable(NavRoute.Benchmark.route) { BenchmarkScreen() }
            composable(NavRoute.Settings.route)  { SettingsScreen() }
        }
    }
}

@Composable
private fun EdgeLLMBottomBar(navController: NavHostController) {
    val navBackStackEntry by navController.currentBackStackEntryAsState()
    val currentRoute = navBackStackEntry?.destination?.route

    NavigationBar {
        bottomNavItems.forEach { screen ->
            NavigationBarItem(
                icon  = { Icon(screen.icon, contentDescription = screen.label) },
                label = { Text(screen.label) },
                selected = currentRoute == screen.route,
                onClick = {
                    navController.navigate(screen.route) {
                        // Avoid building up a large back-stack
                        popUpTo(navController.graph.startDestinationId) { saveState = true }
                        launchSingleTop = true
                        restoreState = true
                    }
                },
            )
        }
    }
}
