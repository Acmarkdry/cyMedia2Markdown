import httpService from './http'
import { APIResponse } from './types'

export const getQueueStatus = async (): Promise<any> => {
  const response = await httpService.request<APIResponse<any>>({
    url: '/api/v1/queue/status',
    method: 'GET'
  })

  if (!response.success || !response.data) {
    throw new Error(response.error?.message || '读取队列状态失败')
  }

  return response.data
}
