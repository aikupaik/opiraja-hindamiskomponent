import { api, type CourseChoice } from './adminApi'

export function loadCourses(signal?: AbortSignal): Promise<CourseChoice[]> {
  return api<CourseChoice[]>('/api/v1/admin/courses', { signal })
}
