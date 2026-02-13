import { Database } from 'lucide-react'
import { ContentGallery } from './ContentGallery'

export function DatabasePage() {
  return (
    <div className="stack">
      <div className="flex items-center gap-2">
        <Database size={20} />
        <h1 className="text-xl font-semibold">Database</h1>
      </div>
      <ContentGallery />
    </div>
  )
}
