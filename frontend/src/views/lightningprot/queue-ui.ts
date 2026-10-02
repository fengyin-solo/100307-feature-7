/** 防雷复测队列共用的展示口径：状态配色、天数文案、结论标签。 */

export type QueueItem = {
  id: number
  装置编号: string
  所属站点: string
  接地电阻: number | null
  防雷模块: string
  浪涌保护: string
  上次测试: string
  测试人员: string
  装置状态: string
  下次复测日: string
  距复测天数: number | null
  队列状态: string
  in_queue: boolean
  degraded: boolean
  超标说明: string
  测试记录: Array<Record<string, string | number>>
  更换记录: Array<Record<string, string | number>>
}

export type QueueSettings = {
  cycle_months: number
  warn_days: number
  resistance_limit: number
}

/** 队列徽章配色。 */
export function queueClass(state: unknown): string {
  const text = String(state ?? '')
  if (text.includes('超标')) return 'tag-bad'
  if (text === '已超期' || text.includes('已超期')) return 'tag-danger'
  if (text === '即将到期') return 'tag-warn'
  if (text.includes('劣化')) return 'tag-warn'
  if (text === '已安排') return 'tag-info'
  return 'tag-ok'
}

/** 装置状态徽章配色。 */
export function stateClass(state: unknown): string {
  const text = String(state ?? '')
  if (text.includes('超标')) return 'tag-bad'
  if (text.includes('劣化')) return 'tag-warn'
  if (text === '已更换') return 'tag-info'
  return 'tag-ok'
}

/** 距复测天数的可读文案。 */
export function daysLabel(days: number | null): string {
  if (days === null || days === undefined) return '未排期'
  if (days < 0) return `已超期 ${Math.abs(days)} 天`
  if (days === 0) return '今天到期'
  return `还剩 ${days} 天`
}
