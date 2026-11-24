// Draws the IELTS-study app icon (1024×1024 PNG). Usage: swift make_icon.swift out.png
import AppKit

let size: CGFloat = 1024
let out = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "icon.png"

let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: Int(size), pixelsHigh: Int(size),
                           bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                           colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
NSColor.clear.setFill()
NSRect(x: 0, y: 0, width: size, height: size).fill()

func color(_ hex: UInt32, _ alpha: CGFloat = 1) -> NSColor {
    NSColor(srgbRed: CGFloat((hex >> 16) & 0xff) / 255, green: CGFloat((hex >> 8) & 0xff) / 255,
            blue: CGFloat(hex & 0xff) / 255, alpha: alpha)
}
// Coordinates below are top-down (like CSS); flip into AppKit's bottom-up space.
func rect(_ x: CGFloat, _ y: CGFloat, _ w: CGFloat, _ h: CGFloat) -> NSRect {
    NSRect(x: x, y: size - y - h, width: w, height: h)
}
func pill(_ r: NSRect, _ fill: NSColor) {
    fill.setFill()
    NSBezierPath(roundedRect: r, xRadius: r.height / 2, yRadius: r.height / 2).fill()
}

// Background: macOS-style rounded square with a soft shadow and a navy gradient.
let tile = rect(100, 100, 824, 824)
let shadow = NSShadow()
shadow.shadowColor = color(0x0b1220, 0.35)
shadow.shadowBlurRadius = 28
shadow.shadowOffset = NSSize(width: 0, height: -12)
NSGraphicsContext.saveGraphicsState()
shadow.set()
let tilePath = NSBezierPath(roundedRect: tile, xRadius: 186, yRadius: 186)
color(0x24385c).setFill()
tilePath.fill()
NSGraphicsContext.restoreGraphicsState()
NSGradient(starting: color(0x3d5b8f), ending: color(0x1b2a45))!.draw(in: tilePath, angle: -90)

// "IELTS" wordmark.
let para = NSMutableParagraphStyle()
para.alignment = .center
let font = NSFont.systemFont(ofSize: 214, weight: .heavy)
let title = NSAttributedString(string: "IELTS", attributes: [
    .font: font, .foregroundColor: NSColor.white, .paragraphStyle: para, .kern: 4,
])
title.draw(in: rect(100, 232, 824, 260))

// Subtitle lines: the first carries an orange highlighted "word", like the app's hard-word mark.
pill(rect(236, 590, 552, 76), color(0xffffff, 0.94))
pill(rect(452, 590, 196, 76), color(0xf2a54a))
pill(rect(306, 702, 412, 60), color(0xffffff, 0.5))

NSGraphicsContext.restoreGraphicsState()
try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: out))
print("wrote \(out)")
