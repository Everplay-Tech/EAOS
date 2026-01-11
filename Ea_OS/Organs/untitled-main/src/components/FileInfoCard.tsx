import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import type { FileData } from '@/types/file'
import { formatBytes, formatDate } from '@/lib/fileUtils'
import { File, Calendar, FileCode, HardDrive } from '@phosphor-icons/react'

interface FileInfoCardProps {
  fileData: FileData
}

export function FileInfoCard({ fileData }: FileInfoCardProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <File className="text-primary" />
          File Information
        </CardTitle>
        <CardDescription>Metadata about the uploaded file</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <File size={16} />
              Name
            </div>
            <div className="text-sm font-mono text-foreground break-all text-right">
              {fileData.name}
            </div>
          </div>
          
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <HardDrive size={16} />
              Size
            </div>
            <div className="text-sm text-foreground text-right">
              {formatBytes(fileData.size)}
              <span className="text-muted-foreground ml-2">
                ({fileData.size.toLocaleString()} bytes)
              </span>
            </div>
          </div>
          
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <FileCode size={16} />
              Type
            </div>
            <div className="text-right">
              <Badge variant="secondary">
                {fileData.type || 'unknown'}
              </Badge>
            </div>
          </div>
          
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <Calendar size={16} />
              Modified
            </div>
            <div className="text-sm text-foreground text-right">
              {formatDate(fileData.lastModified)}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
