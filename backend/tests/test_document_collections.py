import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import (
    Base,
    CollectionGroupPermission,
    CollectionUserPermission,
    Document,
    DocumentCollection,
    Group,
    User,
    UserGroup,
)
from app.services import document_collection_service, document_service


class DocumentCollectionPermissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.admin = User(
            username="admin",
            hashed_password="test",
            is_active=True,
            is_admin=True,
        )
        self.reader = User(
            username="reader",
            hashed_password="test",
            is_active=True,
            is_admin=False,
        )
        self.group_reader = User(
            username="group_reader",
            hashed_password="test",
            is_active=True,
            is_admin=False,
        )
        self.db.add_all([self.admin, self.reader, self.group_reader])
        self.db.flush()
        self.collection = DocumentCollection(
            name="食品安全国标",
            description="测试文档集",
            owner_id=self.admin.id,
        )
        self.group = Group(name="法规部", description="测试部门")
        self.db.add_all([self.collection, self.group])
        self.db.flush()
        self.document = Document(
            filename="GB-test.pdf",
            file_type="pdf",
            content_type="application/pdf",
            storage_path="test.pdf",
            file_size=100,
            status="indexed",
            status_message="done",
            chunk_count=1,
            owner_id=self.admin.id,
            collection_id=self.collection.id,
        )
        self.db.add(self.document)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_collection_user_permission_expands_document_access(self) -> None:
        self.assertEqual(document_service.list_accessible_documents(self.db, self.reader), [])
        self.db.add(
            CollectionUserPermission(
                collection_id=self.collection.id,
                user_id=self.reader.id,
                can_read=True,
                can_write=False,
            )
        )
        self.db.commit()

        accessible = document_service.list_accessible_documents(self.db, self.reader)

        self.assertEqual([item.id for item in accessible], [self.document.id])
        self.assertIsNotNone(
            document_service.get_accessible_document(
                self.db,
                self.document.id,
                self.reader,
            )
        )
        self.assertIsNone(
            document_service.get_writable_document(
                self.db,
                self.document.id,
                self.reader,
            )
        )

    def test_collection_group_permission_is_inherited(self) -> None:
        self.db.add(
            UserGroup(group_id=self.group.id, user_id=self.group_reader.id)
        )
        self.db.add(
            CollectionGroupPermission(
                collection_id=self.collection.id,
                group_id=self.group.id,
                can_read=True,
                can_write=True,
            )
        )
        self.db.commit()

        accessible = document_service.list_accessible_documents(
            self.db,
            self.group_reader,
        )

        self.assertEqual([item.id for item in accessible], [self.document.id])
        self.assertIsNotNone(
            document_service.get_writable_document(
                self.db,
                self.document.id,
                self.group_reader,
            )
        )

    def test_admin_move_and_collection_delete_preserve_document(self) -> None:
        target = DocumentCollection(
            name="乳制品标准",
            owner_id=self.admin.id,
        )
        self.db.add(target)
        self.db.commit()
        result = document_collection_service.move_documents(
            self.db,
            [self.document.id],
            target.id,
            actor=self.admin,
        )
        self.db.refresh(self.document)

        self.assertEqual(result["moved_count"], 1)
        self.assertEqual(self.document.collection_id, target.id)

        deleted = document_collection_service.delete_collection(
            self.db,
            target.id,
            actor=self.admin,
        )
        self.db.expire_all()

        self.assertTrue(deleted)
        preserved = self.db.get(Document, self.document.id)
        self.assertIsNotNone(preserved)
        self.assertIsNone(preserved.collection_id)


if __name__ == "__main__":
    unittest.main()
