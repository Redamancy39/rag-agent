from sqlalchemy import select

from app.core.config import get_settings
from app.core.logger import get_logger
from app.core.security import get_password_hash
from app.db.session import SessionLocal, engine
from app.models import (
    AuditLog,
    Base,
    ChatJob,
    ChatLog,
    CollectionGroupPermission,
    CollectionUserPermission,
    Document,
    DocumentCollection,
    DocumentProcessingJob,
    Group,
    GroupPermission,
    Permission,
    User,
    UserGroup,
)

logger = get_logger(__name__)


def init_db() -> None:
    settings = get_settings()
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    settings.CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    settings.LOG_DIR.mkdir(parents=True, exist_ok=True)

    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_schema()
    _seed_superuser()


def _ensure_sqlite_schema() -> None:
    settings = get_settings()
    if not settings.DATABASE_URL.startswith("sqlite"):
        return

    document_columns = {
        "content_type": "VARCHAR(128)",
        "file_size": "INTEGER DEFAULT 0",
        "status_message": "VARCHAR(512)",
        "chunk_count": "INTEGER DEFAULT 0",
        "error_message": "TEXT",
        "collection_id": "INTEGER",
        "updated_at": "DATETIME",
    }
    job_columns = {
        "probe_json": "TEXT",
        "plan_json": "TEXT",
        "options_json": "TEXT",
        "trace_json": "TEXT",
        "progress_total": "INTEGER DEFAULT 0",
        "progress_current": "INTEGER DEFAULT 0",
        "progress_percent": "INTEGER DEFAULT 0",
        "progress_detail": "VARCHAR(512)",
    }
    with engine.begin() as connection:
        rows = connection.exec_driver_sql("PRAGMA table_info(documents)").fetchall()
        existing_columns = {row[1] for row in rows}
        for column_name, column_definition in document_columns.items():
            if column_name not in existing_columns:
                connection.exec_driver_sql(
                    f"ALTER TABLE documents ADD COLUMN {column_name} {column_definition}"
                )
                logger.info("Added missing documents.%s column", column_name)

        rows = connection.exec_driver_sql(
            "PRAGMA table_info(document_processing_jobs)"
        ).fetchall()
        existing_columns = {row[1] for row in rows}
        for column_name, column_definition in job_columns.items():
            if column_name not in existing_columns:
                connection.exec_driver_sql(
                    "ALTER TABLE document_processing_jobs "
                    f"ADD COLUMN {column_name} {column_definition}"
                )
                logger.info(
                    "Added missing document_processing_jobs.%s column",
                    column_name,
                )

        chat_job_columns = {
            "message": "VARCHAR(512)",
            "error_message": "TEXT",
            "document_ids_json": "TEXT",
            "progress_percent": "INTEGER DEFAULT 0",
            "progress_detail": "VARCHAR(512)",
            "trace_json": "TEXT",
            "response_json": "TEXT",
            "log_id": "INTEGER",
            "started_at": "DATETIME",
            "finished_at": "DATETIME",
            "updated_at": "DATETIME",
        }
        rows = connection.exec_driver_sql("PRAGMA table_info(chat_jobs)").fetchall()
        existing_columns = {row[1] for row in rows}
        for column_name, column_definition in chat_job_columns.items():
            if column_name not in existing_columns:
                connection.exec_driver_sql(
                    f"ALTER TABLE chat_jobs ADD COLUMN {column_name} {column_definition}"
                )
                logger.info("Added missing chat_jobs.%s column", column_name)

        chat_log_columns = {
            "retrieval_trace_json": "TEXT",
            "query_plan_json": "TEXT",
            "evidence_decision_json": "TEXT",
            "citation_validation_json": "TEXT",
            "retrieval_scope_json": "TEXT",
            "response_json": "TEXT",
        }
        rows = connection.exec_driver_sql("PRAGMA table_info(chat_logs)").fetchall()
        existing_columns = {row[1] for row in rows}
        for column_name, column_definition in chat_log_columns.items():
            if column_name not in existing_columns:
                connection.exec_driver_sql(
                    f"ALTER TABLE chat_logs ADD COLUMN {column_name} {column_definition}"
                )
                logger.info("Added missing chat_logs.%s column", column_name)

        audit_log_columns = {
            "collection_id": "INTEGER",
        }
        rows = connection.exec_driver_sql("PRAGMA table_info(audit_logs)").fetchall()
        existing_columns = {row[1] for row in rows}
        for column_name, column_definition in audit_log_columns.items():
            if column_name not in existing_columns:
                connection.exec_driver_sql(
                    f"ALTER TABLE audit_logs ADD COLUMN {column_name} {column_definition}"
                )
                logger.info("Added missing audit_logs.%s column", column_name)

        audit_foreign_keys = connection.exec_driver_sql(
            "PRAGMA foreign_key_list(audit_logs)"
        ).fetchall()
        if audit_foreign_keys:
            connection.exec_driver_sql("ALTER TABLE audit_logs RENAME TO audit_logs_old")
            AuditLog.__table__.create(bind=connection)
            connection.exec_driver_sql(
                """
                INSERT INTO audit_logs (
                    id, actor_user_id, action, target_type, target_id,
                    document_id, user_id, group_id, collection_id, detail_json, created_at
                )
                SELECT
                    id, actor_user_id, action, target_type, target_id,
                    document_id, user_id, group_id, collection_id, detail_json, created_at
                FROM audit_logs_old
                """
            )
            connection.exec_driver_sql("DROP TABLE audit_logs_old")
            logger.info("Rebuilt audit_logs table without target foreign keys")


def _seed_superuser() -> None:
    settings = get_settings()
    if not settings.FIRST_SUPERUSER_USERNAME or not settings.FIRST_SUPERUSER_PASSWORD:
        return

    with SessionLocal() as db:
        existing_user = db.scalar(
            select(User).where(User.username == settings.FIRST_SUPERUSER_USERNAME)
        )
        if existing_user:
            return

        user = User(
            username=settings.FIRST_SUPERUSER_USERNAME,
            hashed_password=get_password_hash(settings.FIRST_SUPERUSER_PASSWORD),
            is_active=True,
            is_admin=True,
        )
        db.add(user)
        db.commit()
        logger.info("Seeded initial superuser: %s", settings.FIRST_SUPERUSER_USERNAME)
