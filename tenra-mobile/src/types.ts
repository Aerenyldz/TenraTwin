export interface CallRecord {
  id: number;
  caller_name: string;
  timestamp: string;
  urgency: 'onemli' | 'normal' | 'oylesine' | string;
  summary: string;
  transcript: string;
  audio_file?: string;
}

export interface DialogueMessage {
  role: 'user' | 'assistant';
  content: string;
  audio_url?: string;
}

export interface AssistantStatus {
  status: string;
  status_detail: string;
}

export interface ServerConfig {
  url: string;
  mode: 'tailscale' | 'local' | 'cloud' | 'custom';
}
