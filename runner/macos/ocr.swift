// OCR one image with Vision (no TCC needed); prints "x,y,w,h\ttext" per line.
// With a crop rect (x y w h, top-left origin, same space as screencapture PNG
// pixels), coordinates are offset back to full-image pixels.
import Foundation
import Vision
import AppKit

let args = CommandLine.arguments
guard args.count >= 2 else { exit(2) }
let url = URL(fileURLWithPath: args[1])
guard let image = NSImage(contentsOf: url),
      let tiff = image.tiffRepresentation,
      let bitmap = NSBitmapImageRep(data: tiff) else { exit(3) }
var cg = bitmap.cgImage!
var ox = 0, oy = 0
if args.count >= 6 {
    let x = Int(args[2])!, y = Int(args[3])!, w = Int(args[4])!, h = Int(args[5])!
    if let cropped = cg.cropping(to: CGRect(x: x, y: y, width: w, height: h)) {
        cg = cropped
        ox = x; oy = y
    }
}
let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = false
let handler = VNImageRequestHandler(cgImage: cg, options: [:])
try handler.perform([request])
let results = (request.results ?? []) as [VNRecognizedTextObservation]
for obs in results {
    if let top = obs.topCandidates(1).first {
        let box = obs.boundingBox
        let w = Double(cg.width), h = Double(cg.height)
        let px = box.origin.x * w + Double(ox), py = (1.0 - box.origin.y - box.height) * h + Double(oy)
        print(String(format: "%.0f,%.0f,%.0f,%.0f\t", px, py, box.width * w, box.height * h) + top.string)
    }
}
