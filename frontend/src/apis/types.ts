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

export interface MediaFromUrlResponse {
  media_id: string;
  url_hash: string;
  title: string;
  source_url: string;
  audio_filename: string;
  video_filename: string;
  duration: number | null;
  cache_hit?: boolean;
  cache_source?: string;
  transcript_source?: string;
  subtitle_filename?: string;
  subtitle_language?: string;
  subtitle_source?: string;
  transcript_segments?: Array<{
    id?: number;
    start_time: number;
    end_time: number;
    text: string;
  }>;
  transcript_segments_count?: number;
}

export interface VideoScreenshotResponse {
  time_seconds: number;
  filename: string;
  data_url: string;
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
  error: string | null;
  filename?: string | null;
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
  error: string | null;
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

/**
 * 文章来源信息
 */
export interface ArticleSource {
  /** 文章URL */
  url: string;
  /** 文章标题（提取后填充） */
  title?: string;
}

/**
 * 文章元数据
 */
export interface ArticleMetadata {
  author?: string;
  date?: string;
  description?: string;
  sitename?: string;
}

/**
 * 单篇文章提取结果
 */
export interface ArticleExtractResult {
  /** 原始URL */
  url: string;
  /** 文章标题 */
  title?: string;
  /** 提取的Markdown内容 */
  markdown_content: string;
  /** HTML内容 */
  html_content?: string;
  /** 提取方式 */
  extraction_method: string;
  /** 文章元数据 */
  metadata?: ArticleMetadata;
  /** 关键要点 */
  key_points?: string;
}

/**
 * 本地代码工程配置
 */
export interface LocalCodeProject {
  path: string;
  label: string;
  file_patterns?: string[];
}

/**
 * 代码文件信息
 */
export interface CodeFile {
  project_label: string;
  relative_path: string;
  content: string;
  language: string;
}

/**
 * 赛博洗稿请求参数
 */
export interface ArticleWashingRequest {
  /** 文章来源列表 */
  articles: ArticleSource[];
  /** 本地代码工程列表 */
  code_projects?: LocalCodeProject[];
  /** 上下文提示：描述这些文章是关于什么的 */
  context_prompt: string;
  /** 洗稿提示：用于深化提取的prompt */
  refinement_prompt: string;
  /** 输出风格 */
  style?: string;
  /** LLM超时时间（秒） */
  timeout?: number;
  /** LLM最大token数 */
  max_tokens?: number;
}

/**
 * 赛博洗稿响应结果
 */
export interface ArticleWashingResponse {
  /** 提取的各篇文章内容 */
  extracted_articles: ArticleExtractResult[];
  /** 代码文件列表 */
  code_files?: CodeFile[];
  /** 领域知识脉络 */
  domain_summary: string;
  /** 最终洗稿后的Markdown内容 */
  refined_output: string;
  /** Stage 1 提示词 */
  stage1_prompt?: string;
  /** Stage 2 提示词 */
  stage2_prompt?: string;
}

/**
 * 读取代码工程请求
 */
export interface ReadCodeRequest {
  projects: LocalCodeProject[];
  max_files_per_project?: number;
}

/**
 * 读取代码工程响应
 */
export interface ReadCodeResponse {
  files: CodeFile[];
  errors?: Array<{ path: string; error: string }>;
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
  LOCAL_MEDIA_DIR: string | null;
  LOCAL_SCREENSHOT_DIR: string | null;
  YTDLP_COOKIES_FILE: string | null;
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
