export function downloadTextFile(fileName: string, contents: string, mimeType: string) {
  const blob = new Blob([contents], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function isImageLikeFile(file: File) {
  return file.type.startsWith("image/") || /\.(png|jpe?g|bmp|webp)$/i.test(file.name);
}

export function isVideoLikeFile(file: File) {
  return file.type.startsWith("video/") || /\.(mp4|mov|mkv|avi|webm)$/i.test(file.name);
}

export function pendingFileRoleLabel(file: File) {
  if (isImageLikeFile(file)) {
    return "图片";
  }
  if (isVideoLikeFile(file)) {
    return "视频";
  }
  return "其他";
}

export function formatFileSize(bytes: number) {
  if (bytes <= 0) {
    return "0 B";
  }
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  if (bytes < 1024 * 1024 * 1024) {
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}
