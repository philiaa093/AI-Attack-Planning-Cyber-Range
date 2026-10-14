export interface ModelProfile {
  id: string;
  name: string;
  protocol: 'openai-compatible' | 'anthropic';
  model: string;
  endpoint: string;
  has_api_key: boolean;
  connection_status: 'NOT_TESTED';
}

export interface ModelProfileInput {
  name: string;
  protocol: ModelProfile['protocol'];
  model: string;
  endpoint: string;
  api_key: string;
  clear_key: boolean;
}
