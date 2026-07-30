# Play Store feature graphic — 1024x500, in The Desk's own system:
# white sheet on paper ground, hairline rules, Instrument Sans + Plex Mono.
Add-Type -AssemblyName System.Drawing

$repo = "C:\Users\Salim\Desktop\code\claude\carthago"
$fonts = New-Object System.Drawing.Text.PrivateFontCollection
$fonts.AddFontFile("$repo\mobile\node_modules\@expo-google-fonts\instrument-sans\600SemiBold\InstrumentSans_600SemiBold.ttf")
$fonts.AddFontFile("$repo\mobile\node_modules\@expo-google-fonts\instrument-sans\400Regular\InstrumentSans_400Regular.ttf")
$fonts.AddFontFile("$repo\mobile\node_modules\@expo-google-fonts\ibm-plex-mono\400Regular\IBMPlexMono_400Regular.ttf")

$semi = New-Object System.Drawing.FontFamily("Instrument Sans SemiBold", $fonts)
if (-not $semi) { $semi = $fonts.Families[0] }
$sans = $fonts.Families | Where-Object { $_.Name -like "Instrument Sans*" } | Select-Object -First 1
$mono = $fonts.Families | Where-Object { $_.Name -like "IBM Plex Mono*" } | Select-Object -First 1

$W = 1024; $H = 500
$bmp = New-Object System.Drawing.Bitmap($W, $H, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::ClearTypeGridFit
$g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality

function C($hex) { [System.Drawing.ColorTranslator]::FromHtml($hex) }

# Paper ground, then the sheet floating on it with a hairline edge.
$g.Clear((C "#F7F8F6"))
$sheet = New-Object System.Drawing.Rectangle(36, 36, ($W - 72), ($H - 72))
$g.FillRectangle((New-Object System.Drawing.SolidBrush((C "#FFFFFF"))), $sheet)
$g.DrawRectangle((New-Object System.Drawing.Pen((C "#E1E3DD"), 1)), $sheet)

# The mark.
$mark = [System.Drawing.Image]::FromFile("$repo\web\app\icon.png")
$g.DrawImage($mark, 92, 150, 150, 150)
$mark.Dispose()

$x = 288
# Use the SemiBold FAMILY, not a synthesised Bold style on the Regular family —
# GDI+ fakes the weight otherwise and the wordmark renders thin.
$semiFam = $fonts.Families | Where-Object { $_.Name -eq "Instrument Sans SemiBold" } | Select-Object -First 1
$g.DrawString("Carthago", (New-Object System.Drawing.Font($semiFam, 66, [System.Drawing.FontStyle]::Regular)),
  (New-Object System.Drawing.SolidBrush((C "#12161B"))), ($x - 6), 148)
$g.DrawString("Turkish banking sector data", (New-Object System.Drawing.Font($sans, 25)),
  (New-Object System.Drawing.SolidBrush((C "#50565E"))), ($x - 3), 246)

$g.DrawLine((New-Object System.Drawing.Pen((C "#ECEDE8"), 1)), $x, 300, ($W - 92), 300)

$g.DrawString("AUDITED BRSA FILINGS  /  BDDK AGGREGATES  /  TCMB MACRO",
  (New-Object System.Drawing.Font($mono, 14)),
  (New-Object System.Drawing.SolidBrush((C "#6A6E73"))), ($x - 2), 318)

# A single navy sparkline — the hero mark, one series, exactly as the app plots it.
$pts = @(0.30, 0.42, 0.38, 0.55, 0.50, 0.62, 0.58, 0.72, 0.66, 0.80, 0.74, 0.88)
$x0 = $x; $x1 = $W - 92; $yb = 430; $hh = 74
$path = New-Object System.Drawing.Drawing2D.GraphicsPath
for ($i = 0; $i -lt $pts.Count - 1; $i++) {
  $ax = $x0 + ($x1 - $x0) * $i / ($pts.Count - 1)
  $bx = $x0 + ($x1 - $x0) * ($i + 1) / ($pts.Count - 1)
  $ay = $yb - $hh * $pts[$i]
  $by = $yb - $hh * $pts[$i + 1]
  $path.AddLine($ax, $ay, $bx, $by)
}
$g.DrawPath((New-Object System.Drawing.Pen((C "#2B4E7E"), 2.5)), $path)
$lastX = $x1; $lastY = $yb - $hh * $pts[$pts.Count - 1]
$g.FillEllipse((New-Object System.Drawing.SolidBrush((C "#2B4E7E"))), ($lastX - 4), ($lastY - 4), 8, 8)

$g.Dispose()
$out = "C:\Users\Salim\AppData\Local\Temp\claude\C--Users-Salim-Desktop-code-claude-carthago\17f67d8c-5f14-4583-b9ec-76839eb5306b\scratchpad\feature-graphic.png"
$bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
Write-Output "saved: $out"
Write-Output ("fonts loaded: " + (($fonts.Families | ForEach-Object { $_.Name }) -join ", "))
