/**
 * 后端统一API响应格式
 */
export interface APIResponse<T = any> {
  success: boolean;
  message: string;
  data: T | null;
  error: {
    code: string;
    message: string;
    details: any;
  } | null;
}

/**
 * Chat API响应格式
 */
export interface ChatResponse {
  id: string;
  choices: {
    message: {
      role: string;
      content: string;
    };
    index: number;
    finish_reason: string;
  }[];
  created: number;
  model: string;
  object: string;
  usage: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  } | null;
}

/**
 * 聊天消息接口
 */
export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

/**
 * 文件上传URL响应
 */
export interface UploadUrlResponse {
  upload_url: string;
}

/**
 * ASR任务提交响应
 */
export interface SubmitAsrTaskResponse {
  task_id: string;
}

/**
 * ASR任务查询响应
 */
export interface QueryASRTaskResponse {
  status: string;
  result: Array<{
    start_time: number;
    end_time: number;
    text: string;
  }> | null;
}

/**
 * 任务状态类型
 */
export type TaskStatus = 'running' | 'finished' | 'failed';

/**
 * 音频任务结果接口
 */
export interface AudioTaskResult {
  text: Array<Record<string, any>> | null;
  status: TaskStatus;
}

/**
 * 内容风格类型
 */
export type ContentStyle = 'note' | 'summary' | 'xiaohongshu' | 'wechat' | 'mind';

/**
 * 任务记录接口
 */
export interface Task {
  id?: number;
  fileName: string;
  md5: string;
  transcriptionText: string;
  markdownContent: string;
  contentStyle: ContentStyle;
  createdAt: string;
}

// 兼容旧代码的类型别名
export interface AudioTaskResponse extends UploadUrlResponse {}

/**
 * 健康检查 data 响应结构
 * 示例:
 * {
 *   "success": true,
 *   "message": "Service is healthy",
 *   "data": { "status": "healthy", "timestamp": 1757084110 },
 *   "error": null
 * }
 */
export interface HealthCheckResponse {
  status: string;      // 示例: "healthy"
  timestamp: number;   // Unix 时间戳
}

/**
 * 后端 /api/v1/secrets 返回的环境变量数据
 * 说明: 部分值可能已做脱敏或为 null
 */
export interface SecretsData {
  CODEX_CLI_PATH: string | null;
  CODEX_CLI_MODEL: string | null;
  CODEX_CLI_REASONING_EFFORT: string | null;
  LOCAL_UPLOAD_DIR: string | null;
  ASR_PROVIDER: string | null;
  ASR_LANGUAGE: string | null;
  FASTER_WHISPER_MODEL: string | null;
  FASTER_WHISPER_DEVICE: string | null;
  FASTER_WHISPER_COMPUTE_TYPE: string | null;
  WEB_ACCESS_PASSWORD: string | null;
}

/**
 * /api/v1/secrets 响应（顶层仍用通用 APIResponse）
 */
export type SecretsResponse = APIResponse<SecretsData>;
