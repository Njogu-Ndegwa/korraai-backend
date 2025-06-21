# knowledge_base/utils.py
import asyncio
import json
import time
import hashlib
from typing import List, Dict, Optional
from openai import OpenAI
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from .models import KnowledgeBaseDocument, DocumentChunk, DocumentEmbedding

# Initialize OpenAI client
openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)


class DocumentProcessor:
    """Handle JSON document processing, chunking, and embedding generation"""
    
    def __init__(self):
        self.embedding_model = "text-embedding-3-small"
        self.max_retries = 3
    
    async def process_json_document(self, document: KnowledgeBaseDocument, 
                                  regenerate_chunks: bool = False) -> Dict:
        """Process JSON document to create chunks and embeddings"""
        
        try:
            # Update processing status
            document.processing_status = 'processing'
            document.save(update_fields=['processing_status', 'updated_at'])
            
            # Delete existing chunks if regenerating
            if regenerate_chunks:
                DocumentChunk.objects.filter(document=document).delete()
            
            # Check if chunks already exist
            existing_chunks = DocumentChunk.objects.filter(document=document).count()
            if existing_chunks > 0 and not regenerate_chunks:
                return {
                    'success': True,
                    'message': f'Document already has {existing_chunks} chunks. Use regenerate_chunks=True to recreate.',
                    'chunks_created': 0,
                    'embeddings_created': 0
                }
            
            # Parse JSON content
            try:
                json_data = json.loads(document.content)
                if not isinstance(json_data, list):
                    raise ValueError("JSON content must be a list of objects")
            except (json.JSONDecodeError, ValueError) as e:
                document.processing_status = 'failed'
                document.metadata = {
                    **(document.metadata or {}),
                    'error_message': f'Invalid JSON format: {str(e)}'
                }
                document.save(update_fields=['processing_status', 'metadata', 'updated_at'])
                
                return {
                    'success': False,
                    'message': f'Invalid JSON format: {str(e)}',
                    'chunks_created': 0,
                    'embeddings_created': 0
                }
            
            # Create chunks from JSON objects
            chunk_data_list = self.create_json_chunks(json_data, document.title)
            
            if not chunk_data_list:
                document.processing_status = 'failed'
                document.metadata = {
                    **(document.metadata or {}),
                    'error_message': 'No valid objects found in JSON'
                }
                document.save(update_fields=['processing_status', 'metadata', 'updated_at'])
                
                return {
                    'success': False,
                    'message': 'No valid objects found in JSON',
                    'chunks_created': 0,
                    'embeddings_created': 0
                }
            
            # Create chunk objects in database
            chunks_created = []
            with transaction.atomic():
                for chunk_data in chunk_data_list:
                    chunk = DocumentChunk.objects.create(
                        tenant=document.tenant,
                        document=document,
                        **chunk_data
                    )
                    chunks_created.append(chunk)
            
            # Generate embeddings for chunks
            embeddings_created = 0
            failed_embeddings = 0
            
            for chunk in chunks_created:
                try:
                    # Create embedding text with context
                    embedding_text = f"Document: {document.title}\n\nContent: {chunk.content}"
                    
                    embedding_vector = await self.generate_embedding(embedding_text)
                    
                    if embedding_vector:
                        DocumentEmbedding.objects.create(
                            tenant=document.tenant,
                            document=document,
                            chunk=chunk,
                            embedding_model=self.embedding_model,
                            embedding_vector=embedding_vector,
                            vector_dimension=len(embedding_vector)
                        )
                        embeddings_created += 1
                    else:
                        failed_embeddings += 1
                        print(f"Failed to generate embedding for chunk {chunk.chunk_index}")
                
                except Exception as e:
                    failed_embeddings += 1
                    print(f"Error creating embedding for chunk {chunk.chunk_index}: {str(e)}")
                
                # Small delay to avoid rate limiting
                await asyncio.sleep(0.1)
            
            # Update document status
            if failed_embeddings == 0:
                document.processing_status = 'completed'
            elif embeddings_created > 0:
                document.processing_status = 'completed'
                document.metadata = {
                    **(document.metadata or {}),
                    'partial_embeddings': f'{failed_embeddings} embeddings failed'
                }
            else:
                document.processing_status = 'failed'
                document.metadata = {
                    **(document.metadata or {}),
                    'error_message': 'All embeddings failed to generate'
                }
            
            document.processed_at = timezone.now()
            document.save(update_fields=['processing_status', 'metadata', 'processed_at', 'updated_at'])
            
            return {
                'success': True,
                'message': f'Successfully processed document with {len(chunks_created)} chunks and {embeddings_created} embeddings',
                'chunks_created': len(chunks_created),
                'embeddings_created': embeddings_created,
                'failed_embeddings': failed_embeddings,
                'json_objects_processed': len(json_data)
            }
        
        except Exception as e:
            # Update document status on failure
            document.processing_status = 'failed'
            document.metadata = {
                **(document.metadata or {}),
                'error_message': str(e),
                'processing_failed_at': timezone.now().isoformat()
            }
            document.save(update_fields=['processing_status', 'metadata', 'updated_at'])
            
            return {
                'success': False,
                'message': f'Processing failed: {str(e)}',
                'chunks_created': 0,
                'embeddings_created': 0
            }
    
    def create_json_chunks(self, json_data: List[Dict], document_title: str) -> List[Dict]:
        """Create chunks from JSON objects, maintaining object structure"""
        chunks = []
        
        for index, obj in enumerate(json_data):
            if not isinstance(obj, dict):
                continue
                
            # Convert object to structured text
            chunk_content = self.json_object_to_text(obj)
            
            if not chunk_content.strip():
                continue
            
            # Calculate word count
            word_count = len(chunk_content.split())
            
            # Create content hash
            content_hash = hashlib.md5(chunk_content.encode()).hexdigest()
            
            chunk_data = {
                'chunk_index': index,
                'content': chunk_content,
                'content_hash': content_hash,
                'word_count': word_count,
                'chunk_metadata': {
                    'json_object_index': index,
                    'object_keys': list(obj.keys()),
                    'object_name': obj.get('name', f'Object {index}'),
                    'chunk_type': 'json_object',
                    'extraction_method': 'json_structured'
                }
            }
            
            chunks.append(chunk_data)
        
        return chunks
    
    def json_object_to_text(self, obj: Dict) -> str:
        """Convert JSON object to structured text for better embeddings"""
        lines = []
        
        # Add object name/title if available
        if 'name' in obj:
            lines.append(f"Name: {obj['name']}")
        elif 'title' in obj:
            lines.append(f"Title: {obj['title']}")
        
        # Process each field
        for key, value in obj.items():
            if key in ['name', 'title']:
                continue  # Already processed above
                
            if isinstance(value, str):
                # Clean up the text
                clean_value = value.strip()
                if clean_value:
                    lines.append(f"{key.replace('_', ' ').title()}: {clean_value}")
            
            elif isinstance(value, (int, float)):
                lines.append(f"{key.replace('_', ' ').title()}: {value}")
            
            elif isinstance(value, list):
                if value:  # Only if list is not empty
                    list_str = ", ".join([str(item) for item in value])
                    lines.append(f"{key.replace('_', ' ').title()}: {list_str}")
            
            elif isinstance(value, dict):
                # Flatten nested objects
                for nested_key, nested_value in value.items():
                    if isinstance(nested_value, str) and nested_value.strip():
                        lines.append(f"{key.replace('_', ' ').title()} {nested_key.replace('_', ' ').title()}: {nested_value.strip()}")
        
        return "\n".join(lines)
    
    async def generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding for text with retry logic"""
        print("------250------")
        for attempt in range(self.max_retries):
            try:
                response = openai_client.embeddings.create(
                    input=text,
                    model=self.embedding_model
                )
                return response.data[0].embedding
            
            except Exception as e:
                if "rate_limit" in str(e).lower():
                    wait_time = min(2 ** attempt, 60)  # Exponential backoff, max 60s
                    print(f"Rate limit hit. Waiting {wait_time}s before retry {attempt + 1}/{self.max_retries}")
                    await asyncio.sleep(wait_time)
                else:
                    print(f"Error generating embedding on attempt {attempt + 1}: {str(e)}")
                    if attempt == self.max_retries - 1:
                        return None
                    await asyncio.sleep(1)
        
        return None
    
    async def generate_embeddings_for_document(self, document: KnowledgeBaseDocument,
                                             regenerate_embeddings: bool = False) -> Dict:
        """Generate embeddings for existing document chunks"""
        
        chunks = DocumentChunk.objects.filter(document=document)
        
        if not chunks.exists():
            return {
                'success': False,
                'message': 'No chunks found for document',
                'embeddings_created': 0
            }
        
        # Delete existing embeddings if regenerating
        if regenerate_embeddings:
            DocumentEmbedding.objects.filter(document=document).delete()
        
        # Check existing embeddings
        existing_embeddings = DocumentEmbedding.objects.filter(document=document).count()
        if existing_embeddings > 0 and not regenerate_embeddings:
            return {
                'success': True,
                'message': f'Document already has {existing_embeddings} embeddings. Use regenerate_embeddings=True to recreate.',
                'embeddings_created': 0
            }
        
        embeddings_created = 0
        failed_embeddings = 0
        print("300")
        for chunk in chunks:
            try:
                embedding_text = f"Document: {document.title}\n\nContent: {chunk.content}"
                embedding_vector = await self.generate_embedding(embedding_text)
                print("------305------")
                if embedding_vector:
                    DocumentEmbedding.objects.create(
                        tenant=document.tenant,
                        document=document,
                        chunk=chunk,
                        embedding_model=self.embedding_model,
                        embedding_vector=embedding_vector,
                        vector_dimension=len(embedding_vector)
                    )
                    embeddings_created += 1
                else:
                    failed_embeddings += 1
                
                # Small delay to avoid rate limiting
                await asyncio.sleep(0.1)
                
            except Exception as e:
                failed_embeddings += 1
                print(f"Error creating embedding for chunk {chunk.chunk_index}: {str(e)}")
        
        return {
            'success': True,
            'message': f'Generated {embeddings_created} embeddings, {failed_embeddings} failed',
            'embeddings_created': embeddings_created,
            'failed_embeddings': failed_embeddings
        }