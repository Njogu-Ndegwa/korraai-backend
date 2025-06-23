# # My Current Consumer File
# import json
# import asyncio
# from datetime import datetime
# from typing import List, Tuple, Dict
# import uuid

# from channels.generic.websocket import AsyncWebsocketConsumer
# from channels.db import database_sync_to_async
# from django.utils import timezone
# from asgiref.sync import sync_to_async
# import openai
# import numpy as np
# from pgvector.django import L2Distance
# from litellm import acompletion, aembedding
# from django.conf import settings

# # Models based on your schema
# from django.db import models
# from conversations.models import Conversation, Message
# from customers.models import Customer
# from knowledgebase.models import DocumentEmbedding, DocumentChunk, KnowledgeRetrievalLog
# from ai.models import AIUsageLog, TenantAISetting
# from tenants.models import Tenant

# openai_key = settings.OPENAI_API_KEY
# client = openai.OpenAI(api_key=openai_key)
# class QAWebSocket(AsyncWebsocketConsumer):
#     """WebSocket endpoint for Q&A with RAG functionality"""
    
#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         # Get config from Django settings or environment
#         self.llm_model = getattr(settings, 'LLM_MODEL', 'openai/gpt-4o-mini')
#         self.llm_api_key = getattr(settings, 'LLM_API_KEY', settings.OPENAI_API_KEY)
#         self.embedding_model = getattr(settings, 'EMBEDDING_MODEL', 'text-embedding-3-small')
    
#     async def connect(self):
#         """Accept WebSocket connection"""
#         self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']
#         await self.accept()
        
#         # Load conversation data
#         self.conversation = await self.get_conversation()
#         if not self.conversation:
#             await self.send(json.dumps({"error": "Invalid conversation ID"}))
#             await self.close()
#             return
            
#         self.tenant = self.conversation.tenant
#         self.customer = self.conversation.customer
#         self.ai_settings = await self.get_ai_settings()
        
#     async def disconnect(self, close_code):
#         """Handle disconnection"""
#         pass
        
#     async def receive(self, text_data):
#         """Handle incoming message and return AI response"""
#         try:
#             data = json.loads(text_data)
#             user_question = data.get('message', '')
            
#             if not user_question:
#                 await self.send(json.dumps({"error": "Empty message"}))
#                 return
#             print("601-----")  
#             # Process the question and get response
#             response = await self.process_question(user_question)
            
#             # Send response back
#             await self.send(json.dumps({
#                 "response": response,
#                 "timestamp": datetime.now().isoformat()
#             }))
            
#         except Exception as e:
#             await self.send(json.dumps({"error": str(e)}))
    
#     async def process_question(self, question: str) -> str:
#         """Main RAG pipeline with context awareness"""
#         start_time = timezone.now()
        
#         # 1. Create user message in MESSAGES table
#         user_message = await self.create_message(
#             content=question,
#             sender_type='customer',
#             direction='inbound'
#         )
        
#         # 2. Get conversation history for context analysis
#         conversation_history = await self.get_conversation_history()
        
        
#         # 3. Analyze if this is a follow-up question or new question
#         analyzed_question = await self.analyze_question(question, conversation_history)
#         # 4. Generate embedding for the analyzed question
#         embedding = await self.generate_embedding(analyzed_question)
        
#         # 5. Search knowledge base with the analyzed question
#         chunks, scores = await self.search_knowledge_base(embedding)
#         # 6. Log retrieval in KNOWLEDGE_RETRIEVAL_LOGS
#         await self.log_retrieval(user_message, analyzed_question, embedding, chunks, scores, start_time)
        
#         # 7. Generate AI response with conversation context
#         context = self.prepare_context(chunks)
#         print(context, "context")
#         ai_response, tokens = await self.generate_ai_response(
#             original_question=question,
#             analyzed_question=analyzed_question,
#             context=context,
#             conversation_history=conversation_history
#         )
        
#         # 8. Create AI message in MESSAGES table
#         ai_message = await self.create_message(
#             content=ai_response,
#             sender_type='ai',
#             direction='outbound',
#             ai_confidence=0.9
#         )
        
#         # 9. Log AI usage in AI_USAGE_LOGS
#         await self.log_ai_usage(user_message, tokens, len(chunks), start_time)
        
#         # 10. Update conversation timestamps
#         await self.update_conversation()
        
#         # 11. Update customer last contact
#         await self.update_customer()
        
#         return ai_response
    
#     async def analyze_question(self, question: str, conversation_history: List[Dict]) -> str:
#         """
#         Analyzes if a question is a follow-up or a unique question.
#         For follow-up questions, it rewrites them with context from previous conversation.
#         For unique questions, it returns the original question.
#         """
#         if not conversation_history:
#             return question  # No conversation history, so must be a unique question
        
#         # Prepare context for the LLM to analyze
#         analysis_prompt = """
# Analyze the following conversation and determine if the latest question is a follow-up question
# or a unique question. If it's a follow-up, rewrite it to include the necessary context.
# If it's a unique question, return the original question unchanged.

# Previous conversation:
# """
        
#         # Add conversation history (last 3 exchanges)
#         for i, exchange in enumerate(conversation_history[-3:]):
#             analysis_prompt += f"\nQ{i+1}: {exchange['question']}\nA{i+1}: {exchange['answer']}\n"
        
#         analysis_prompt += f"\nLatest question: {question}\n\nInstructions:\n"
#         analysis_prompt += """
# 1. If this is a follow-up question that relies on previous context (contains pronouns like "it", "they", 
#    "this", "that", refers to something previously discussed, or is incomplete without context), 
#    rewrite it to be self-contained with relevant context.
# 2. If this is a brand new question unrelated to previous exchanges, return the original question unchanged.
# 3. Start your response with either "REWRITTEN:" followed by the rewritten question, or "ORIGINAL:" 
#    followed by the unchanged question.
# """
        
#         # Use LiteLLM to analyze the question
#         messages = [
#             {"role": "system", "content": "You are an AI assistant that analyzes conversations to determine if questions are follow-ups or unique questions."},
#             {"role": "user", "content": analysis_prompt}
#         ]
#         print(self.llm_api_key, "---wee")
#         response = await acompletion(
#             model=self.llm_model,
#             messages=messages,
#             api_key=self.llm_api_key
#         )
        
#         analysis_result = response.choices[0].message.content.strip()
        
#         # Parse the response to get the analyzed question
#         if analysis_result.startswith("REWRITTEN:"):
#             return analysis_result.replace("REWRITTEN:", "").strip()
#         elif analysis_result.startswith("ORIGINAL:"):
#             return analysis_result.replace("ORIGINAL:", "").strip()
#         else:
#             # If the format is not as expected, return the original question to be safe
#             return question
    
#     @database_sync_to_async
#     def get_conversation_history(self, limit: int = 10) -> List[Dict]:
#         """Get recent conversation history in Q&A format"""
#         recent_messages = Message.objects.filter(
#             conversation=self.conversation,
#             message_type='text'
#         ).order_by('-created_at')[:limit * 2]  # Get 2x limit to ensure we have pairs
        
#         history = []
#         messages_list = list(reversed(recent_messages))
        
#         # Pair up customer questions with AI answers
#         i = 0
#         while i < len(messages_list) - 1:
#             if messages_list[i].sender_type == 'customer' and messages_list[i+1].sender_type == 'ai':
#                 history.append({
#                     'question': messages_list[i].content_encrypted,  # Decrypt in production
#                     'answer': messages_list[i+1].content_encrypted
#                 })
#                 i += 2
#             else:
#                 i += 1
        
#         return history
    
#     @database_sync_to_async
#     def get_conversation(self):
#         """Get conversation with related data"""
#         try:
#             return Conversation.objects.select_related(
#                 'tenant', 'customer', 'platform'
#             ).get(id=self.conversation_id)
#         except Conversation.DoesNotExist:
#             return None
    
#     @database_sync_to_async
#     def get_ai_settings(self):
#         """Get AI settings for tenant"""
#         try:
#             return TenantAISetting.objects.get(
#                 tenant=self.tenant,
#                 platform=self.conversation.platform
#             )
#         except TenantAISetting.DoesNotExist:
#             # Return default settings
#             return type('obj', (object,), {
#                 'max_knowledge_chunks': 5,
#                 'similarity_threshold': 0.7,
#                 'system_prompt': 'You are a helpful AI assistant.'
#             })
    
#     @database_sync_to_async
#     def create_message(self, content, sender_type, direction, ai_confidence=None):
#         """Create message in MESSAGES table"""
#         # Generate a unique external_message_id to avoid duplicate key constraint
#         external_message_id = f"{sender_type}_{uuid.uuid4().hex[:16]}_{int(timezone.now().timestamp())}"
        
#         message = Message.objects.create(
#             tenant=self.tenant,
#             conversation=self.conversation,
#             external_message_id=external_message_id,  # Add unique external message ID
#             message_type='text',
#             direction=direction,
#             sender_type=sender_type,
#             sender_id=self.customer.id if sender_type == 'customer' else None,
#             sender_name=self.customer.platform_display_name if sender_type == 'customer' else 'AI Assistant',
#             content_encrypted=content,  # Add encryption in production
#             content_hash=str(hash(content)),  # Convert to string
#             ai_processed=True if sender_type == 'ai' else False,
#             ai_confidence=ai_confidence,
#             delivery_status='delivered',
#             platform_timestamp=timezone.now()
#         )
#         return message
    
#     async def generate_embedding(self, text: str) -> List[float]:
#         """Generate embedding using OpenAI"""

#         response = await sync_to_async(client.embeddings.create)(
#             model="text-embedding-3-small",
#             input=text
#         )
#         return response.data[0].embedding
    

#     @database_sync_to_async
#     def search_knowledge_base(
#         self,
#         query_embedding: List[float],
#         *,
#         top_k: int = 5,
#     ) -> Tuple[List[dict], List[float]]:
#         """
#         Run similarity search in a thread and return **plain data**:
#         - a list of dictionaries describing each chunk
#         - a parallel list of similarity scores
#         """
#         rows = (
#             DocumentEmbedding.find_top_k(
#                 query_vector=query_embedding,
#                 tenant_id=self.tenant.id,
#                 top_k=top_k,
#                 similarity_threshold=0.1,
#                 embedding_model=self.embedding_model,
#             )
#             .select_related("chunk")
#             .values(                              # <- serialise in SQL
#                 "chunk_id",
#                 "chunk__content",                 # or whatever fields you need
#                 "similarity_score",
#             )
#         )

#         chunk_dicts = [
#             {"id": r["chunk_id"], "content": r["chunk__content"]}
#             for r in rows
#         ]
#         scores = [r["similarity_score"] for r in rows]

#         return chunk_dicts, scores



    
#     def prepare_context(self, chunks: List[DocumentChunk]) -> str:
#         """Prepare context from chunks"""
#         if not chunks:
#             return ""
        
#         parts = [c["content"] for c in chunks]
#         return "\n\n".join(parts)
    
#     async def generate_ai_response(self, original_question: str, analyzed_question: str, 
#                                   context: str, conversation_history: List[Dict]) -> Tuple[str, int]:
#         """Generate response using LiteLLM with conversation awareness"""
        
#         # Build messages with conversation history for better context
#         messages = [
#             {"role": "system", "content": self.ai_settings.system_prompt + f"\n\nRelevant context:\n{context}"}
#         ]
        
#         # Add conversation history
#         for exchange in conversation_history[-5:]:  # Last 5 exchanges for context
#             messages.append({"role": "user", "content": exchange['question']})
#             messages.append({"role": "assistant", "content": exchange['answer']})
        
#         # Add the current question (use original, not analyzed, for natural conversation flow)
#         messages.append({"role": "user", "content": original_question})
        
#         print(messages, "Messages")
#         response = await acompletion(
#             model=self.llm_model,
#             messages=messages,
#             api_key=self.llm_api_key
#         )
        
#         # Extract token usage - LiteLLM response structure might vary by provider
#         tokens_used = getattr(response.usage, 'total_tokens', 0)
        
#         return response.choices[0].message.content, tokens_used
    
#     @database_sync_to_async
#     def log_retrieval(self, message, query_text, embedding, chunks, scores, start_time):
#         """Create entry in KNOWLEDGE_RETRIEVAL_LOGS"""
#         KnowledgeRetrievalLog.objects.create(
#             tenant=self.tenant,
#             conversation=self.conversation,
#             message=message,
#             query_text=query_text,
#             query_embedding=embedding,
#             retrieved_chunks=[{"chunk_id": str(c["id"])} for c in chunks],
#             similarity_scores=scores,
#             chunks_used_count=len(chunks),
#             retrieval_time_ms=int((timezone.now() - start_time).total_seconds() * 1000)
#         )
    
#     @database_sync_to_async
#     def log_ai_usage(self, message, tokens, chunks_used, start_time):
#         """Create entry in AI_USAGE_LOGS"""
#         AIUsageLog.objects.create(
#             tenant=self.tenant,
#             conversation=self.conversation,
#             message=message,
#             usage_date=timezone.now().date(),
#             tokens_used=tokens,
#             processing_time_ms=int((timezone.now() - start_time).total_seconds() * 1000),
#             confidence_score=0.9,
#             knowledge_chunks_used=chunks_used,
#             handover_triggered=False
#         )
    
#     @database_sync_to_async
#     def update_conversation(self):
#         """Update CONVERSATIONS table"""
#         self.conversation.last_message_at = timezone.now()
#         self.conversation.last_ai_response_at = timezone.now()
#         self.conversation.save(update_fields=['last_message_at', 'last_ai_response_at'])
    
#     @database_sync_to_async
#     def update_customer(self):
#         """Update CUSTOMERS table"""
#         self.customer.last_contact_at = timezone.now()
#         self.customer.last_seen_at = timezone.now()
#         self.customer.save(update_fields=['last_contact_at', 'last_seen_at'])


# conversations/consumers.py
import json
import asyncio
from datetime import datetime
from typing import List, Tuple, Dict
import uuid

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from asgiref.sync import sync_to_async
import openai
import numpy as np
from pgvector.django import L2Distance
from litellm import acompletion, aembedding
from django.conf import settings

# Models based on your schema
from django.db import models
from conversations.models import Conversation, Message
from customers.models import Customer
from knowledgebase.models import DocumentEmbedding, DocumentChunk, KnowledgeRetrievalLog
from ai.models import AIUsageLog, TenantAISetting
from tenants.models import Tenant
from platforms.models import TenantPlatformAccount
from platforms.webhook_views import PlatformMessenger

openai_key = settings.OPENAI_API_KEY
client = openai.OpenAI(api_key=openai_key)

class QAWebSocket(AsyncWebsocketConsumer):
    """WebSocket endpoint for Q&A with RAG functionality and platform integration"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Get config from Django settings or environment
        self.llm_model = getattr(settings, 'LLM_MODEL', 'openai/gpt-4o-mini')
        self.llm_api_key = getattr(settings, 'LLM_API_KEY', settings.OPENAI_API_KEY)
        self.embedding_model = getattr(settings, 'EMBEDDING_MODEL', 'text-embedding-3-small')
    
    async def connect(self):
        """Accept WebSocket connection"""
        self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']
        self.room_group_name = f"rag_processor_{self.conversation_id}"
        
        # Join conversation group for RAG processing
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
        
        # Load conversation data
        self.conversation = await self.get_conversation()
        if not self.conversation:
            await self.send(json.dumps({"error": "Invalid conversation ID"}))
            await self.close()
            return
            
        self.tenant = self.conversation.tenant
        self.customer = self.conversation.customer
        self.platform_account = self.conversation.platform_account
        self.ai_settings = await self.get_ai_settings()
        
    async def disconnect(self, close_code):
        """Handle disconnection"""
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        
    async def receive(self, text_data):
        """Handle incoming message and return AI response"""
        try:
            data = json.loads(text_data)
            user_question = data.get('message', '')
            
            if not user_question:
                await self.send(json.dumps({"error": "Empty message"}))
                return
                
            # Process the question and get response
            response = await self.process_question(user_question)
            
            # Send response back
            await self.send(json.dumps({
                "response": response,
                "timestamp": datetime.now().isoformat()
            }))
            
        except Exception as e:
            await self.send(json.dumps({"error": str(e)}))
    
    async def process_message(self, event):
        """Handle message from webhook - called when platform sends message"""
        try:
            message = event['message']
            conversation_id = event['conversation_id']
            
            # Verify this is the right conversation
            if conversation_id != str(self.conversation_id):
                return
                
            # Process the incoming platform message
            response = await self.process_question(message, from_platform=True)
            
            # Send response back to platform instead of WebSocket
            await self.send_platform_response(response)
            
        except Exception as e:
            logger.error(f"Error processing platform message: {e}")
    
    async def process_question(self, question: str, from_platform: bool = False) -> str:
        """Main RAG pipeline with context awareness and platform integration"""
        start_time = timezone.now()
        
        # If not from platform, create user message (platform messages already created in webhook)
        if not from_platform:
            user_message = await self.create_message(
                content=question,
                sender_type='customer',
                direction='inbound'
            )
        else:
            # Get the latest customer message for this conversation
            user_message = await self.get_latest_customer_message()
        
        # 2. Get conversation history for context analysis
        conversation_history = await self.get_conversation_history()
        
        # 3. Analyze if this is a follow-up question or new question
        analyzed_question = await self.analyze_question(question, conversation_history)
        
        # 4. Generate embedding for the analyzed question
        embedding = await self.generate_embedding(analyzed_question)
        
        # 5. Search knowledge base with the analyzed question
        chunks, scores = await self.search_knowledge_base(embedding)
        
        # 6. Log retrieval in KNOWLEDGE_RETRIEVAL_LOGS
        await self.log_retrieval(user_message, analyzed_question, embedding, chunks, scores, start_time)
        
        # 7. Generate AI response with conversation context
        context = self.prepare_context(chunks)
        ai_response, tokens = await self.generate_ai_response(
            original_question=question,
            analyzed_question=analyzed_question,
            context=context,
            conversation_history=conversation_history
        )
        
        # 8. Create AI message in MESSAGES table
        ai_message = await self.create_message(
            content=ai_response,
            sender_type='ai',
            direction='outbound',
            ai_confidence=0.9
        )
        
        # 9. Log AI usage in AI_USAGE_LOGS
        await self.log_ai_usage(user_message, tokens, len(chunks), start_time)
        
        # 10. Update conversation timestamps
        await self.update_conversation()
        
        # 11. Update customer last contact
        await self.update_customer()
        
        return ai_response
    
    async def send_platform_response(self, response: str):
        """Send AI response back to the platform where message originated"""
        try:
            platform_name = self.conversation.platform.name
            customer_external_id = self.customer.external_id
            
            if platform_name == 'facebook':
                success = await PlatformMessenger.send_facebook_message(
                    customer_external_id, 
                    response, 
                    self.platform_account
                )
            elif platform_name == 'whatsapp':
                success = await PlatformMessenger.send_whatsapp_message(
                    customer_external_id, 
                    response, 
                    self.platform_account
                )
            else:
                logger.warning(f"Unsupported platform: {platform_name}")
                return
                
            if success:
                # Update message delivery status
                await self.update_message_delivery_status()
            else:
                logger.error(f"Failed to send message to {platform_name}")
                
        except Exception as e:
            logger.error(f"Error sending platform response: {e}")
    
    @database_sync_to_async
    def get_latest_customer_message(self):
        """Get the latest customer message for this conversation"""
        return Message.objects.filter(
            conversation=self.conversation,
            sender_type='customer'
        ).order_by('-created_at').first()
    
    @database_sync_to_async
    def update_message_delivery_status(self):
        """Update the latest AI message delivery status"""
        latest_ai_message = Message.objects.filter(
            conversation=self.conversation,
            sender_type='ai'
        ).order_by('-created_at').first()
        
        if latest_ai_message:
            latest_ai_message.delivery_status = 'delivered'
            latest_ai_message.save(update_fields=['delivery_status'])
    
    async def analyze_question(self, question: str, conversation_history: List[Dict]) -> str:
        """
        Analyzes if a question is a follow-up or a unique question.
        For follow-up questions, it rewrites them with context from previous conversation.
        For unique questions, it returns the original question.
        """
        if not conversation_history:
            return question  # No conversation history, so must be a unique question
        
        # Prepare context for the LLM to analyze
        analysis_prompt = """
Analyze the following conversation and determine if the latest question is a follow-up question
or a unique question. If it's a follow-up, rewrite it to include the necessary context.
If it's a unique question, return the original question unchanged.

Previous conversation:
"""
        
        # Add conversation history (last 3 exchanges)
        for i, exchange in enumerate(conversation_history[-3:]):
            analysis_prompt += f"\nQ{i+1}: {exchange['question']}\nA{i+1}: {exchange['answer']}\n"
        
        analysis_prompt += f"\nLatest question: {question}\n\nInstructions:\n"
        analysis_prompt += """
1. If this is a follow-up question that relies on previous context (contains pronouns like "it", "they", 
   "this", "that", refers to something previously discussed, or is incomplete without context), 
   rewrite it to be self-contained with relevant context.
2. If this is a brand new question unrelated to previous exchanges, return the original question unchanged.
3. Start your response with either "REWRITTEN:" followed by the rewritten question, or "ORIGINAL:" 
   followed by the unchanged question.
"""
        
        # Use LiteLLM to analyze the question
        messages = [
            {"role": "system", "content": "You are an AI assistant that analyzes conversations to determine if questions are follow-ups or unique questions."},
            {"role": "user", "content": analysis_prompt}
        ]
        
        response = await acompletion(
            model=self.llm_model,
            messages=messages,
            api_key=self.llm_api_key
        )
        
        analysis_result = response.choices[0].message.content.strip()
        
        # Parse the response to get the analyzed question
        if analysis_result.startswith("REWRITTEN:"):
            return analysis_result.replace("REWRITTEN:", "").strip()
        elif analysis_result.startswith("ORIGINAL:"):
            return analysis_result.replace("ORIGINAL:", "").strip()
        else:
            # If the format is not as expected, return the original question to be safe
            return question
    
    @database_sync_to_async
    def get_conversation_history(self, limit: int = 10) -> List[Dict]:
        """Get recent conversation history in Q&A format"""
        recent_messages = Message.objects.filter(
            conversation=self.conversation,
            message_type='text'
        ).order_by('-created_at')[:limit * 2]  # Get 2x limit to ensure we have pairs
        
        history = []
        messages_list = list(reversed(recent_messages))
        
        # Pair up customer questions with AI answers
        i = 0
        while i < len(messages_list) - 1:
            if messages_list[i].sender_type == 'customer' and messages_list[i+1].sender_type == 'ai':
                history.append({
                    'question': messages_list[i].content_encrypted,  # Decrypt in production
                    'answer': messages_list[i+1].content_encrypted
                })
                i += 2
            else:
                i += 1
        
        return history
    
    @database_sync_to_async
    def get_conversation(self):
        """Get conversation with related data"""
        try:
            return Conversation.objects.select_related(
                'tenant', 'customer', 'platform', 'platform_account'
            ).get(id=self.conversation_id)
        except Conversation.DoesNotExist:
            return None
    
    @database_sync_to_async
    def get_ai_settings(self):
        """Get AI settings for tenant"""
        try:
            return TenantAISetting.objects.get(
                tenant=self.tenant,
                platform=self.conversation.platform
            )
        except TenantAISetting.DoesNotExist:
            # Return default settings
            return type('obj', (object,), {
                'max_knowledge_chunks': 5,
                'similarity_threshold': 0.7,
                'system_prompt': 'You are a helpful AI assistant.'
            })
    
    @database_sync_to_async
    def create_message(self, content, sender_type, direction, ai_confidence=None):
        """Create message in MESSAGES table"""
        # Generate a unique external_message_id to avoid duplicate key constraint
        external_message_id = f"{sender_type}_{uuid.uuid4().hex[:16]}_{int(timezone.now().timestamp())}"
        
        message = Message.objects.create(
            tenant=self.tenant,
            conversation=self.conversation,
            external_message_id=external_message_id,
            message_type='text',
            direction=direction,
            sender_type=sender_type,
            sender_id=self.customer.id if sender_type == 'customer' else None,
            sender_name=self.customer.platform_display_name if sender_type == 'customer' else 'AI Assistant',
            content_encrypted=content,  # Add encryption in production
            content_hash=str(hash(content)),
            ai_processed=True if sender_type == 'ai' else False,
            ai_confidence=ai_confidence,
            delivery_status='delivered',
            platform_timestamp=timezone.now()
        )
        return message
    
    async def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding using OpenAI"""
        response = await sync_to_async(client.embeddings.create)(
            model="text-embedding-3-small",
            input=text
        )
        return response.data[0].embedding
    
    @database_sync_to_async
    def search_knowledge_base(
        self,
        query_embedding: List[float],
        *,
        top_k: int = 5,
    ) -> Tuple[List[dict], List[float]]:
        """
        Run similarity search in a thread and return **plain data**:
        - a list of dictionaries describing each chunk
        - a parallel list of similarity scores
        """
        rows = (
            DocumentEmbedding.find_top_k(
                query_vector=query_embedding,
                tenant_id=self.tenant.id,
                top_k=top_k,
                similarity_threshold=0.1,
                embedding_model=self.embedding_model,
            )
            .select_related("chunk")
            .values(
                "chunk_id",
                "chunk__content",
                "similarity_score",
            )
        )

        chunk_dicts = [
            {"id": r["chunk_id"], "content": r["chunk__content"]}
            for r in rows
        ]
        scores = [r["similarity_score"] for r in rows]

        return chunk_dicts, scores
    
    def prepare_context(self, chunks: List[DocumentChunk]) -> str:
        """Prepare context from chunks"""
        if not chunks:
            return ""
        
        parts = [c["content"] for c in chunks]
        return "\n\n".join(parts)
    
    async def generate_ai_response(self, original_question: str, analyzed_question: str, 
                                  context: str, conversation_history: List[Dict]) -> Tuple[str, int]:
        """Generate response using LiteLLM with conversation awareness"""
        
        # Build messages with conversation history for better context
        messages = [
            {"role": "system", "content": self.ai_settings.system_prompt + f"\n\nRelevant context:\n{context}"}
        ]
        
        # Add conversation history
        for exchange in conversation_history[-5:]:  # Last 5 exchanges for context
            messages.append({"role": "user", "content": exchange['question']})
            messages.append({"role": "assistant", "content": exchange['answer']})
        
        # Add the current question (use original, not analyzed, for natural conversation flow)
        messages.append({"role": "user", "content": original_question})
        
        response = await acompletion(
            model=self.llm_model,
            messages=messages,
            api_key=self.llm_api_key
        )
        
        # Extract token usage - LiteLLM response structure might vary by provider
        tokens_used = getattr(response.usage, 'total_tokens', 0)
        
        return response.choices[0].message.content, tokens_used
    
    @database_sync_to_async
    def log_retrieval(self, message, query_text, embedding, chunks, scores, start_time):
        """Create entry in KNOWLEDGE_RETRIEVAL_LOGS"""
        KnowledgeRetrievalLog.objects.create(
            tenant=self.tenant,
            conversation=self.conversation,
            message=message,
            query_text=query_text,
            query_embedding=embedding,
            retrieved_chunks=[{"chunk_id": str(c["id"])} for c in chunks],
            similarity_scores=scores,
            chunks_used_count=len(chunks),
            retrieval_time_ms=int((timezone.now() - start_time).total_seconds() * 1000)
        )
    
    @database_sync_to_async
    def log_ai_usage(self, message, tokens, chunks_used, start_time):
        """Create entry in AI_USAGE_LOGS"""
        AIUsageLog.objects.create(
            tenant=self.tenant,
            conversation=self.conversation,
            message=message,
            usage_date=timezone.now().date(),
            tokens_used=tokens,
            processing_time_ms=int((timezone.now() - start_time).total_seconds() * 1000),
            confidence_score=0.9,
            knowledge_chunks_used=chunks_used,
            handover_triggered=False
        )
    
    @database_sync_to_async
    def update_conversation(self):
        """Update CONVERSATIONS table"""
        self.conversation.last_message_at = timezone.now()
        self.conversation.last_ai_response_at = timezone.now()
        self.conversation.save(update_fields=['last_message_at', 'last_ai_response_at'])
    
    @database_sync_to_async
    def update_customer(self):
        """Update CUSTOMERS table"""
        self.customer.last_contact_at = timezone.now()
        self.customer.last_seen_at = timezone.now()
        self.customer.save(update_fields=['last_contact_at', 'last_seen_at'])


class ConversationMonitorConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for monitoring conversations and handling human takeover"""
    
    async def connect(self):
        """Accept WebSocket connection for conversation monitoring"""
        self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']
        self.user = self.scope['user']
        
        # Join conversation group
        self.room_group_name = f"conversation_{self.conversation_id}"
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
        
        # Send conversation history
        await self.send_conversation_history()
    
    async def disconnect(self, close_code):
        """Handle disconnection"""
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
    
    async def receive(self, text_data):
        """Handle incoming messages from human agents"""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'take_over':
                await self.handle_takeover()
            elif message_type == 'send_message':
                message_content = data.get('message', '')
                await self.handle_human_message(message_content)
            elif message_type == 'pause_ai':
                await self.handle_pause_ai(data.get('reason', ''))
            elif message_type == 'resume_ai':
                await self.handle_resume_ai()
                
        except Exception as e:
            await self.send(json.dumps({"error": str(e)}))
    
    async def new_message(self, event):
        """Handle new message broadcast"""
        await self.send(json.dumps({
            'type': 'new_message',
            'message': event['message']
        }))
    
    async def ai_response(self, event):
        """Handle AI response broadcast"""
        await self.send(json.dumps({
            'type': 'ai_response',
            'message': event['message']
        }))
    
    @database_sync_to_async
    def send_conversation_history(self):
        """Send conversation history to monitoring client"""
        try:
            conversation = Conversation.objects.get(id=self.conversation_id)
            messages = Message.objects.filter(
                conversation=conversation
            ).order_by('created_at')[:50]  # Last 50 messages
            
            history = []
            for msg in messages:
                history.append({
                    'id': str(msg.id),
                    'content': msg.content_encrypted,
                    'sender_type': msg.sender_type,
                    'sender_name': msg.sender_name,
                    'timestamp': msg.created_at.isoformat(),
                    'direction': msg.direction
                })
            
            return {
                'type': 'conversation_history',
                'history': history,
                'conversation': {
                    'id': str(conversation.id),
                    'status': conversation.status,
                    'current_handler_type': conversation.current_handler_type,
                    'ai_enabled': conversation.ai_enabled,
                    'customer_name': conversation.customer.platform_display_name or conversation.customer.platform_username
                }
            }
        except Exception as e:
            return {'type': 'error', 'message': str(e)}
    
    @database_sync_to_async
    def handle_takeover(self):
        """Handle human agent taking over conversation"""
        try:
            conversation = Conversation.objects.get(id=self.conversation_id)
            conversation.current_handler_type = 'human'
            conversation.assigned_user_id = self.user.id
            conversation.ai_enabled = False
            conversation.save(update_fields=['current_handler_type', 'assigned_user_id', 'ai_enabled'])
            
            return {'success': True, 'message': 'Conversation taken over by human agent'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    @database_sync_to_async
    def handle_pause_ai(self, reason):
        """Pause AI for this conversation"""
        try:
            conversation = Conversation.objects.get(id=self.conversation_id)
            conversation.ai_paused_by_user_id = self.user.id
            conversation.ai_paused_at = timezone.now()
            conversation.ai_pause_reason = reason
            conversation.ai_enabled = False
            conversation.save(update_fields=[
                'ai_paused_by_user_id', 'ai_paused_at', 
                'ai_pause_reason', 'ai_enabled'
            ])
            
            return {'success': True, 'message': 'AI paused for conversation'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    @database_sync_to_async
    def handle_resume_ai(self):
        """Resume AI for this conversation"""
        try:
            conversation = Conversation.objects.get(id=self.conversation_id)
            conversation.ai_paused_by_user_id = None
            conversation.ai_paused_at = None
            conversation.ai_pause_reason = None
            conversation.ai_enabled = True
            conversation.current_handler_type = 'ai'
            conversation.assigned_user_id = None
            conversation.save(update_fields=[
                'ai_paused_by_user_id', 'ai_paused_at', 'ai_pause_reason',
                'ai_enabled', 'current_handler_type', 'assigned_user_id'
            ])
            
            return {'success': True, 'message': 'AI resumed for conversation'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def handle_human_message(self, message_content):
        """Handle message sent by human agent"""
        try:
            # Create human message
            conversation = await database_sync_to_async(
                Conversation.objects.get
            )(id=self.conversation_id)
            
            message = await database_sync_to_async(Message.objects.create)(
                tenant=conversation.tenant,
                conversation=conversation,
                external_message_id=f"human_{uuid.uuid4().hex[:16]}_{int(timezone.now().timestamp())}",
                message_type='text',
                direction='outbound',
                sender_type='human',
                sender_id=self.user.id,
                sender_name=f"{self.user.first_name} {self.user.last_name}",
                content_encrypted=message_content,
                content_hash=str(hash(message_content)),
                delivery_status='pending',
                platform_timestamp=timezone.now()
            )
            
            # Send to platform
            platform_name = conversation.platform.name
            customer_external_id = conversation.customer.external_id
            platform_account = conversation.platform_account
            
            if platform_name == 'facebook':
                success = await PlatformMessenger.send_facebook_message(
                    customer_external_id, 
                    message_content, 
                    platform_account
                )
            elif platform_name == 'whatsapp':
                success = await PlatformMessenger.send_whatsapp_message(
                    customer_external_id, 
                    message_content, 
                    platform_account
                )
            else:
                success = False
                
            # Update delivery status
            if success:
                message.delivery_status = 'delivered'
            else:
                message.delivery_status = 'failed'
            
            await database_sync_to_async(message.save)(update_fields=['delivery_status'])
            
            # Broadcast to monitoring clients
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'new_message',
                    'message': {
                        'id': str(message.id),
                        'content': message.content_encrypted,
                        'sender_type': message.sender_type,
                        'sender_name': message.sender_name,
                        'timestamp': message.created_at.isoformat(),
                        'direction': message.direction,
                        'delivery_status': message.delivery_status
                    }
                }
            )
            
        except Exception as e:
            await self.send(json.dumps({"error": f"Failed to send message: {str(e)}"}))


import logging
logger = logging.getLogger(__name__)