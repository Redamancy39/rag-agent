import unittest
from unittest.mock import Mock

from app.rag.schemas import DocumentChunk
from app.rag.vector_store import ChromaVectorStore
from app.rag.vector_batches import VectorBatchWriteError

class VectorBatchTests(unittest.TestCase):
    def store(self, limit):
        store=ChromaVectorStore.__new__(ChromaVectorStore)
        store.max_batch_size=limit
        store.collection=Mock()
        return store

    def test_reported_5603_case_splits_without_losing_alignment(self):
        store=self.store(5461)
        ids=[f'synthetic:{i}' for i in range(5603)]
        chunks=[DocumentChunk(text=f'chunk {i}',metadata={'chunk_index':i,'unset':None}) for i in range(5603)]
        embeddings=[[float(i)] for i in range(5603)]
        store.add_documents(ids,chunks,embeddings)
        calls=store.collection.add.call_args_list
        self.assertEqual([len(call.kwargs['ids']) for call in calls],[5461,142])
        self.assertEqual([value for call in calls for value in call.kwargs['ids']],ids)
        self.assertEqual([value for call in calls for value in call.kwargs['embeddings']],embeddings)
        for call in calls:
            for chunk_id,text,embedding,metadata in zip(call.kwargs['ids'],call.kwargs['documents'],call.kwargs['embeddings'],call.kwargs['metadatas'],strict=True):
                i=int(chunk_id.split(':')[1])
                self.assertEqual((text,embedding,metadata),(f'chunk {i}',[float(i)],{'chunk_index':i}))

    def test_exact_limit_remains_one_batch(self):
        store=self.store(2)
        store.add_documents(['a','b'],[DocumentChunk(text='a',metadata={}),DocumentChunk(text='b',metadata={})],[[1.],[2.]])
        self.assertEqual(store.collection.add.call_count,1)

    def test_mismatch_rejected_before_any_write(self):
        store=self.store(2)
        with self.assertRaisesRegex(ValueError,'count mismatch'):
            store.add_documents(['a'],[],[[1.]])
        store.collection.add.assert_not_called()

    def test_empty_input_does_not_write(self):
        store=self.store(2)
        store.add_documents([],[],[])
        store.collection.add.assert_not_called()

    def test_failure_is_not_silently_accepted(self):
        store=self.store(1)
        store.collection.add.side_effect=[None,RuntimeError('synthetic write failure')]
        with self.assertRaisesRegex(RuntimeError,'write failure'):
            store.add_documents(['a','b'],[DocumentChunk(text='a',metadata={}),DocumentChunk(text='b',metadata={})],[[1.],[2.]])

    def test_invalid_limits_rejected_before_any_write(self):
        for limit in (0, -1, True, 2.5):
            with self.subTest(limit=limit):
                store=self.store(limit)
                with self.assertRaisesRegex(ValueError,'invalid maximum'):
                    store.add_documents(['a'],[DocumentChunk(text='a',metadata={})],[[1.]])
                store.collection.add.assert_not_called()

    def test_duplicate_across_batch_boundary_is_rejected(self):
        store=self.store(1)
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            store.add_documents(['a','a'],[DocumentChunk(text='a',metadata={}),DocumentChunk(text='b',metadata={})],[[1.],[2.]])
        store.collection.add.assert_not_called()

    def test_dimension_error_in_later_batch_is_rejected_before_first_write(self):
        store=self.store(1)
        with self.assertRaisesRegex(ValueError,'dimensions'):
            store.add_documents(['a','b'],[DocumentChunk(text='a',metadata={}),DocumentChunk(text='b',metadata={})],[[1.],[2.,3.]])
        store.collection.add.assert_not_called()

    def test_partial_failure_reports_position_and_clears_success_result(self):
        store=self.store(1)
        store.add_documents(['old'],[DocumentChunk(text='old',metadata={})],[[1.]])
        self.assertEqual(store.last_write_result.row_count,1)
        store.collection.add.side_effect=[None,RuntimeError('synthetic write failure')]
        with self.assertRaises(VectorBatchWriteError) as raised:
            store.add_documents(['a','b','c'],[DocumentChunk(text=i,metadata={}) for i in ('a','b','c')],[[1.],[2.],[3.]])
        self.assertEqual((raised.exception.batch_index,raised.exception.batch_count,raised.exception.completed_count),(2,3,1))
        self.assertIsNone(store.last_write_result)
        self.assertIsInstance(raised.exception.__cause__,RuntimeError)

    def test_empty_vector_rejected_before_any_write(self):
        store=self.store(2)
        with self.assertRaisesRegex(ValueError,'dimensions'):
            store.add_documents(['a'],[DocumentChunk(text='a',metadata={})],[[]])
        store.collection.add.assert_not_called()

    def test_invalid_ids_rejected_before_any_write(self):
        store=self.store(2)
        with self.assertRaisesRegex(ValueError,'nonempty strings'):
            store.add_documents([' '],[DocumentChunk(text='a',metadata={})],[[1.]])
        store.collection.add.assert_not_called()
