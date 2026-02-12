"""
AuditorIA External API - Python SDK Example
Complete integration example for external clients.
"""

import requests
import time
import json
from typing import Optional, Dict, List, Any


class AuditorIAClient:
    """Python client for AuditorIA External API."""

    def __init__(self, base_url: str, api_key: str):
        """
        Initialize the client.

        Args:
            base_url: Base URL of the API (e.g., "http://localhost:8001")
            api_key: Your API key
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.headers = {
            'X-API-Key': api_key
        }

    # ==================== UPLOAD ====================

    def upload_audio(
        self,
        file_path: str,
        campaign_id: int,
        username: str,
        operator_id: int,
        language: str = "es",
        model: str = "nova-3",
        device: str = "deepgram"
    ) -> Dict[str, Any]:
        """
        Upload an audio file for processing.

        Args:
            file_path: Path to the audio file
            campaign_id: Campaign ID for this call
            username: Username of the uploader
            operator_id: Operator ID for this call
            language: Language code (default: "es")
            model: Transcription model (default: "nova-3")
            device: Processing device (default: "deepgram")

        Returns:
            dict: {"task_id": "uuid", "status": "queued", "message": "..."}
        """
        url = f"{self.base_url}/upload/"

        with open(file_path, 'rb') as f:
            files = {'file': f}
            data = {
                'campaign_id': campaign_id,
                'username': username,
                'operator_id': operator_id,
                'language': language,
                'model': model,
                'device': device
            }

            response = requests.post(
                url,
                headers=self.headers,
                files=files,
                data=data
            )
            response.raise_for_status()
            return response.json()

    # ==================== TASKS ====================

    def list_tasks(self, skip: int = 0, limit: int = 10) -> List[Dict]:
        """Get list of tasks."""
        url = f"{self.base_url}/tasks/"
        params = {'skip': skip, 'limit': limit}

        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        return response.json()

    def get_task(self, task_uuid: str) -> Dict[str, Any]:
        """
        Get detailed task information including transcription result.

        Args:
            task_uuid: Task UUID

        Returns:
            dict: Task details with status, result, metadata, error
        """
        url = f"{self.base_url}/tasks/{task_uuid}"

        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def wait_for_task(
        self,
        task_uuid: str,
        timeout: int = 600,
        poll_interval: int = 5
    ) -> Dict[str, Any]:
        """
        Poll task status until completion or timeout.

        Args:
            task_uuid: Task UUID
            timeout: Maximum wait time in seconds (default: 600)
            poll_interval: Seconds between polls (default: 5)

        Returns:
            dict: Final task data

        Raises:
            TimeoutError: If task doesn't complete in time
            Exception: If task fails
        """
        start_time = time.time()

        while True:
            elapsed = time.time() - start_time
            if elapsed > timeout:
                raise TimeoutError(f"Task {task_uuid} did not complete in {timeout}s")

            task_data = self.get_task(task_uuid)
            status = task_data['status']

            if status == 'completed':
                return task_data
            elif status == 'failed':
                error = task_data.get('error', 'Unknown error')
                raise Exception(f"Task failed: {error}")

            print(f"Task {task_uuid} status: {status}, waiting {poll_interval}s...")
            time.sleep(poll_interval)

    def download_audio(self, task_uuid: str, output_path: str) -> None:
        """
        Download audio file for a task.

        Args:
            task_uuid: Task UUID
            output_path: Where to save the audio file
        """
        url = f"{self.base_url}/tasks/{task_uuid}/audio"

        response = requests.get(url, headers=self.headers, stream=True)
        response.raise_for_status()

        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

    def delete_task(self, task_uuid: str) -> None:
        """Delete a task."""
        url = f"{self.base_url}/tasks/{task_uuid}"

        response = requests.delete(url, headers=self.headers)
        response.raise_for_status()

    # ==================== ANALYSIS ====================

    def get_agent_identification(self, task_uuid: str) -> Dict[str, str]:
        """
        Get speaker role identification (agent vs customer).

        Args:
            task_uuid: Task UUID

        Returns:
            dict: {"SPEAKER_00": "Agente", "SPEAKER_01": "Cliente"}
        """
        url = f"{self.base_url}/agent-identification/{task_uuid}"

        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        data = response.json()
        return data['identification']

    def get_speaker_analysis(
        self,
        task_uuid: str,
        generate_new: bool = False
    ) -> Dict[str, str]:
        """
        Get psychological and behavioral analysis of speakers.

        Args:
            task_uuid: Task UUID
            generate_new: Force regeneration (default: False)

        Returns:
            dict: {"SPEAKER_00": "Analysis text...", ...}
        """
        url = f"{self.base_url}/speaker-analysis/{task_uuid}"
        params = {'generate_new': generate_new}

        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        data = response.json()
        return data['analysis']

    def get_tags(
        self,
        task_uuid: str,
        generate_new: bool = False
    ) -> Dict[str, List[str]]:
        """
        Get conversation tags.

        Args:
            task_uuid: Task UUID
            generate_new: Force regeneration (default: False)

        Returns:
            dict: {"tags": [...], "extraTags": [...]}
        """
        url = f"{self.base_url}/tags/{task_uuid}"
        params = {'generate_new': generate_new}

        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        return response.json()

    # ==================== AI CHAT ====================

    def chat(self, task_uuid: str, message: str) -> str:
        """
        Chat with AI about the transcription.

        Args:
            task_uuid: Task UUID
            message: Your question/message

        Returns:
            str: AI response
        """
        url = f"{self.base_url}/tasks/{task_uuid}/chat"
        payload = {'chat_input': message}

        response = requests.post(
            url,
            headers={**self.headers, 'Content-Type': 'application/json'},
            json=payload
        )
        response.raise_for_status()
        return response.json()['response']

    def get_chat_history(self, task_uuid: str) -> List[Dict]:
        """
        Get chat history for a task.

        Args:
            task_uuid: Task UUID

        Returns:
            list: Chat messages
        """
        url = f"{self.base_url}/tasks/{task_uuid}/chat"

        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()['messages']

    # ==================== AUDIT ====================

    def generate_audit(
        self,
        task_uuid: str,
        is_call: bool = True
    ) -> Dict[str, Any]:
        """
        Generate quality audit for a task.

        Args:
            task_uuid: Task UUID
            is_call: Whether this is a call (True) or chat (False)

        Returns:
            dict: Audit results with score, failures, detailed answers
        """
        url = f"{self.base_url}/audit/generate"
        payload = {
            'task_uuid': task_uuid,
            'is_call': is_call
        }

        response = requests.post(
            url,
            headers={**self.headers, 'Content-Type': 'application/json'},
            json=payload
        )
        response.raise_for_status()
        return response.json()

    # ==================== REPORTS ====================

    def get_task_stats(self, days: int = 30) -> Dict[str, Any]:
        """Get task statistics for the last N days."""
        url = f"{self.base_url}/reports/tasks"
        params = {'days': days}

        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        return response.json()

    def get_audit_stats(self, days: int = 30) -> Dict[str, Any]:
        """Get audit statistics for the last N days."""
        url = f"{self.base_url}/reports/audits"
        params = {'days': days}

        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        return response.json()

    def get_summary(self, days: int = 30) -> Dict[str, Any]:
        """Get combined task and audit summary."""
        url = f"{self.base_url}/reports/summary"
        params = {'days': days}

        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        return response.json()

    # ==================== CAMPAIGNS ====================

    def list_campaigns(self) -> List[Dict]:
        """Get list of available campaigns."""
        url = f"{self.base_url}/campaigns/"

        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()


# ==================== USAGE EXAMPLES ====================

def example_complete_workflow():
    """Complete workflow example: upload -> wait -> analyze -> audit."""

    # Initialize client
    client = AuditorIAClient(
        base_url="http://localhost:8001",
        api_key="your-api-key-here"
    )

    # 1. List available campaigns
    print("📋 Fetching campaigns...")
    campaigns = client.list_campaigns()
    print(f"Found {len(campaigns)} campaigns")
    campaign_id = campaigns[0]['campaign_id']

    # 2. Upload audio file
    print("\n📤 Uploading audio file...")
    upload_result = client.upload_audio(
        file_path="path/to/audio.mp3",
        campaign_id=campaign_id,
        username="john_doe",
        operator_id=123
    )
    task_id = upload_result['task_id']
    print(f"✅ Task created: {task_id}")

    # 3. Wait for transcription to complete
    print("\n⏳ Waiting for transcription...")
    task_data = client.wait_for_task(task_id, timeout=600, poll_interval=5)
    print("✅ Transcription completed!")

    # Print transcription
    result = task_data['result']
    print(f"\n📝 Transcription ({result.get('language', 'unknown')}):")
    print(result.get('text', '')[:200] + "...")

    # 4. Get agent identification
    print("\n🔍 Identifying speakers...")
    identification = client.get_agent_identification(task_id)
    print("Agent identification:")
    for speaker, role in identification.items():
        print(f"  {speaker}: {role}")

    # 5. Get speaker analysis
    print("\n🧠 Analyzing speakers...")
    analysis = client.get_speaker_analysis(task_id)
    for speaker, description in analysis.items():
        print(f"\n{speaker}:")
        print(f"  {description[:150]}...")

    # 6. Generate tags
    print("\n🏷️  Generating tags...")
    tags_data = client.get_tags(task_id)
    print(f"Tags: {', '.join(tags_data['tags'])}")
    print(f"Extra tags: {', '.join(tags_data['extraTags'])}")

    # 7. Chat with AI
    print("\n💬 Chatting with AI...")
    response = client.chat(task_id, "¿Cuál fue el motivo de la llamada?")
    print(f"AI: {response}")

    # 8. Generate audit
    print("\n📊 Generating quality audit...")
    audit_result = client.generate_audit(task_id, is_call=True)
    print(f"Score: {audit_result['score']}%")
    print(f"Audit {'FAILED' if audit_result['is_audit_failure'] else 'PASSED'}")
    print("\nCriteria scores:")
    for answer in audit_result['audit']:
        print(f"  - {answer['criterion']}: {answer['score']}/{answer['target_score']}")

    # 9. Download audio
    print("\n💾 Downloading audio...")
    client.download_audio(task_id, "downloaded_audio.mp3")
    print("✅ Audio saved to downloaded_audio.mp3")

    # 10. Get statistics
    print("\n📈 Getting statistics...")
    stats = client.get_summary(days=7)
    print(f"Tasks (last 7 days): {stats['tasks']['total_tasks']}")
    print(f"Audits (last 7 days): {stats['audits']['total_audits']}")
    print(f"Average score: {stats['audits']['average_score']}%")

    print("\n✅ Complete workflow finished successfully!")


def example_batch_processing():
    """Process multiple audio files in batch."""

    client = AuditorIAClient(
        base_url="http://localhost:8001",
        api_key="your-api-key-here"
    )

    audio_files = [
        "call1.mp3",
        "call2.mp3",
        "call3.mp3"
    ]

    # Upload all files
    task_ids = []
    for audio_file in audio_files:
        print(f"Uploading {audio_file}...")
        result = client.upload_audio(
            file_path=audio_file,
            campaign_id=1,
            username="batch_user",
            operator_id=999
        )
        task_ids.append(result['task_id'])
        print(f"  → Task ID: {result['task_id']}")

    # Wait for all to complete
    completed_tasks = []
    for task_id in task_ids:
        print(f"\nWaiting for {task_id}...")
        task_data = client.wait_for_task(task_id)
        completed_tasks.append(task_data)
        print(f"  ✅ Completed")

    # Generate audits for all
    print("\n📊 Generating audits...")
    for task_id in task_ids:
        audit = client.generate_audit(task_id)
        print(f"{task_id}: Score {audit['score']}%")


def example_monitoring():
    """Monitor recent tasks and statistics."""

    client = AuditorIAClient(
        base_url="http://localhost:8001",
        api_key="your-api-key-here"
    )

    # Get recent tasks
    print("📋 Recent tasks:")
    tasks = client.list_tasks(limit=5)
    for task in tasks:
        status_emoji = {
            'completed': '✅',
            'processing': '⏳',
            'pending': '⏸️',
            'failed': '❌'
        }.get(task['status'], '❓')

        print(f"{status_emoji} {task['file_name']}")
        print(f"   Status: {task['status']}")
        print(f"   Duration: {task.get('audio_duration', 'N/A')}s")
        print()

    # Get statistics
    print("\n📈 Statistics (last 30 days):")
    stats = client.get_summary(days=30)

    print(f"Tasks: {stats['tasks']['total_tasks']}")
    print(f"  - Completed: {stats['tasks']['completed']}")
    print(f"  - Failed: {stats['tasks']['failed']}")

    print(f"\nAudits: {stats['audits']['total_audits']}")
    print(f"  - Average score: {stats['audits']['average_score']}%")
    print(f"  - Success rate: {stats['audits']['success_rate']}%")


def example_interactive_chat():
    """Interactive chat session with a transcription."""

    client = AuditorIAClient(
        base_url="http://localhost:8001",
        api_key="your-api-key-here"
    )

    task_id = "your-task-uuid-here"

    print(f"💬 Interactive chat with task {task_id}")
    print("Type 'exit' to quit\n")

    while True:
        question = input("You: ")
        if question.lower() in ['exit', 'quit', 'q']:
            break

        response = client.chat(task_id, question)
        print(f"AI: {response}\n")

    # Show chat history
    print("\n📜 Chat history:")
    history = client.get_chat_history(task_id)
    for msg in history:
        role = msg['role'].upper()
        content = msg['content']
        print(f"{role}: {content}")


if __name__ == "__main__":
    # Run the complete workflow example
    print("=" * 60)
    print("AuditorIA External API - Complete Workflow Example")
    print("=" * 60)

    # Uncomment to run examples:
    # example_complete_workflow()
    # example_batch_processing()
    # example_monitoring()
    # example_interactive_chat()

    print("\n💡 Tip: Edit this file to set your API key and run the examples!")
