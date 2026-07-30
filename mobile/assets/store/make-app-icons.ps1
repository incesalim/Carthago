# Regenerate every mobile icon from the user's own 512px app-icon artwork
# (scripts/brand/carthago-app-icon-512.png).
#
# Two things this handles that a naive resize does not:
#
#  1. The source carries ~57% empty margin — the mark's ink bbox is only 43% of
#     the canvas. Dropped straight into a 1024 icon that reads as a tiny compass
#     in a large white tile at home-screen size. So the mark is cropped to its
#     own bounds and re-framed per target. This is FRAMING, not a redraw: the
#     artwork itself is untouched, only the margin around it changes.
#  2. Android's adaptive-icon mask crops to the central ~66% of the canvas, so
#     the foreground layer is framed tighter than the iOS icon — otherwise a
#     circular launcher mask clips the compass ring.
Add-Type -AssemblyName System.Drawing

$repo = "C:\Users\Salim\Desktop\code\claude\carthago"
$src = New-Object System.Drawing.Bitmap("$repo\scripts\brand\carthago-app-icon-512.png")

# --- ink bounding box (ignore transparent AND near-white pixels) -------------
$minX = $src.Width; $minY = $src.Height; $maxX = 0; $maxY = 0
for ($y = 0; $y -lt $src.Height; $y++) {
  for ($x = 0; $x -lt $src.Width; $x++) {
    $p = $src.GetPixel($x, $y)
    if (($p.A -gt 24) -and -not ($p.R -gt 240 -and $p.G -gt 240 -and $p.B -gt 240)) {
      if ($x -lt $minX) { $minX = $x }; if ($x -gt $maxX) { $maxX = $x }
      if ($y -lt $minY) { $minY = $y }; if ($y -gt $maxY) { $maxY = $y }
    }
  }
}
# Square crop centred on the mark, so nothing is distorted.
$cx = ($minX + $maxX) / 2.0; $cy = ($minY + $maxY) / 2.0
$side = [Math]::Max($maxX - $minX, $maxY - $minY)
$crop = New-Object System.Drawing.Rectangle(
  [int]($cx - $side / 2), [int]($cy - $side / 2), [int]$side, [int]$side)
Write-Output ("ink bbox {0},{1} -> {2},{3}; square crop {4}px" -f $minX, $minY, $maxX, $maxY, [int]$side)

function Render($size, $coverage, $bg, $out) {
  $bmp = New-Object System.Drawing.Bitmap($size, $size, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.InterpolationMode  = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
  $g.SmoothingMode      = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
  $g.PixelOffsetMode    = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
  $g.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
  if ($bg) { $g.Clear([System.Drawing.ColorTranslator]::FromHtml($bg)) }
  else     { $g.Clear([System.Drawing.Color]::Transparent) }
  $d = [int]($size * $coverage); $o = [int](($size - $d) / 2)
  $dest = New-Object System.Drawing.Rectangle($o, $o, $d, $d)
  $g.DrawImage($src, $dest, $crop, [System.Drawing.GraphicsUnit]::Pixel)
  $g.Dispose()
  $bmp.Save((Join-Path $repo $out), [System.Drawing.Imaging.ImageFormat]::Png)
  $bmp.Dispose()
  Write-Output ("  {0,-52} {1}x{1}  mark {2:P0}" -f $out, $size, $coverage)
}

$img = "mobile\assets\images"

# iOS / Play listing icon: MUST be opaque — Apple rejects an alpha channel and
# Play renders transparency as black. 76% is conventional glyph coverage.
Render 1024 0.76 "#FFFFFF" "$img\icon.png"

# Android adaptive layers. Foreground stays inside the 66% mask safe zone.
Render 1024 0.62 $null      "$img\android-icon-foreground.png"
Render 1024 1.00 "#F7F8F6"  "$img\android-icon-background.png"
Render 1024 0.62 $null      "$img\android-icon-monochrome.png"

# Splash mark and web favicon.
Render 512 0.80 $null "$img\splash-icon.png"
Render 48  0.88 $null "$img\favicon.png"

$src.Dispose()
Write-Output "done"
