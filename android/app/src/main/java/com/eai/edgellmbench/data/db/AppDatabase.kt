package com.eai.edgellmbench.data.db

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase

/**
 * Room database for conversation and benchmark history persistence.
 *
 * Version history:
 *   v1 — ConversationEntity, MessageEntity (chat history scaffold)
 *   v2 — Added BenchmarkRunEntity (benchmark history tab)
 *
 * Migration strategy: fallbackToDestructiveMigration on dev builds.
 * Production would use explicit Migration objects.
 */
@Database(
    entities = [ConversationEntity::class, MessageEntity::class, BenchmarkRunEntity::class],
    version  = 2,
    exportSchema = false,
)
abstract class AppDatabase : RoomDatabase() {

    abstract fun conversationDao(): ConversationDao
    abstract fun messageDao(): MessageDao
    abstract fun benchmarkRunDao(): BenchmarkRunDao

    companion object {
        @Volatile private var INSTANCE: AppDatabase? = null

        fun getDatabase(context: Context): AppDatabase {
            return INSTANCE ?: synchronized(this) {
                val instance = Room.databaseBuilder(
                    context.applicationContext,
                    AppDatabase::class.java,
                    "edgellm_history.db",
                ).fallbackToDestructiveMigration().build()
                INSTANCE = instance
                instance
            }
        }
    }
}
