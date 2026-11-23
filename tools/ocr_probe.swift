// OCR one image with Vision (no TCC needed); prints "x,y,w,h\tconfidence\ttext" per line.
import Foundation
import Vision
import AppKit

let args = CommandLine.arguments
guard args.count >= 2 else {
    FileHandle.standardError.write("usage: ocr_probe.swift <image> [crop x y w h]\n".data(using: .utf8)!)
    exit(2)
}
let url = URL(fileURLWithPath: args[1])
guard let image = NSImage(contentsOf: url),
      let tiff = image.tiffRepresentation,
      let bitmap = NSBitmapImageRep(data: tiff) else {
    FileHandle.standardError.write("cannot load image\n".data(using: .utf8)!)
    exit(3)
}
var cg = bitmap.cgImage!
if args.count >= 6 {
    let x = Int(args[2])!, y = Int(args[3])!, w = Int(args[4])!, h = Int(args[5])!
    let rect = CGRect(x: x, y: y, width: w, height: h)
    if let cropped = cg.cropping(to: rect) {
        cg = cropped
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
        // Vision box: origin bottom-left, normalized. Print pixel coords (top-left origin).
        let w = Double(bitmap.pixelsWide), h = Double(bitmap.pixelsHigh)
        let px = box.origin.x * w, py = (1.0 - box.origin.y - box.height) * h
        print(String(format: "%.0f,%.0f,%.0f,%.0f\t%.3f\t", px, py, box.width * w, box.height * h) + top.string)
    }
}
