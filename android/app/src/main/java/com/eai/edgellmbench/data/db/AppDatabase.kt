package com.eai.edgellmbench.data.db

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase

/**
 * Room database for conversation history persistence.
 *
 * Currently scaffolded — conversations are shown in the current session only.
 * Future: wire [ConversationDao] / [MessageDao] to the UI for history browser.
 *
 * Migration strategy:
 *   - On schema change, increment [version] and add a [androidx.room.migration.Migration]
 *     via [Room.databaseBuilder.addMigrations(MIGRATION_1_2)].
 */
@Database(
    entities = [ConversationEntity::class, MessageEntity::class],
    version  = 1,
    exportSchema = false,
)
abstract class AppDatabase : RoomDatabase() {

    abstract fun conversationDao(): ConversationDao
    abstract fun messageDao(): MessageDao

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
