import httpService from './http'
import { APIResponse } from './types'
import type {
  ArticleExtractResult, ArticleWashingRequest, ArticleWashingResponse,
  ReadCodeRequest, ReadCodeResponse
} from './types'

/**
 * 提取单篇文章内容为Markdown
 * @param url 文章URL
 * @param timeout 超时时间（秒）
 * @returns 提取结果
 */
export const extractArticle = async (url: string, timeout: number = 30): Promise<APIResponse<ArticleExtractResult>> => {
  return httpService.request<APIResponse<ArticleExtractResult>>({
    url: '/api/v1/washing/extract',
    method: 'POST',
    data: { url, timeout }
  })
}

/**
 * 赛博洗稿：提取多篇文章并合并洗稿
 * @param request 洗稿请求参数
 * @returns 洗稿结果
 */
export const washArticles = async (request: ArticleWashingRequest): Promise<APIResponse<ArticleWashingResponse>> => {
  return httpService.request<APIResponse<ArticleWashingResponse>>({
    url: '/api/v1/washing/wash',
    method: 'POST',
    data: request
  })
}

/**
 * 读取本地代码工程文件
 * @param request 代码工程读取请求
 * @returns 代码文件列表
 */
export const readCodeProjects = async (request: ReadCodeRequest): Promise<APIResponse<ReadCodeResponse>> => {
  return httpService.request<APIResponse<ReadCodeResponse>>({
    url: '/api/v1/washing/read-code',
    method: 'POST',
    data: request
  })
}