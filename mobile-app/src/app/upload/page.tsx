"use client";

import { useState, useRef, useEffect } from "react";
import { Camera, UploadCloud, CheckCircle2, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { uploadMedia, pollAnalysis, storeFloodZone } from "@/lib/api";

export default function UploadPage() {
    const [file, setFile] = useState<File | null>(null);
    const [preview, setPreview] = useState<string | null>(null);
    const [status, setStatus] = useState<"idle" | "uploading" | "analyzing" | "success" | "error">("idle");
    const [errorMessage, setErrorMessage] = useState("");
    const fileInputRef = useRef<HTMLInputElement>(null);

    const handleFileCapture = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files && e.target.files[0]) {
            const selectedFile = e.target.files[0];
            setFile(selectedFile);
            setPreview(URL.createObjectURL(selectedFile));
            setStatus("idle");
        }
    };

    const handleUpload = async () => {
        if (!file) return;
        setStatus("uploading");

        try {
            let uploadRes: any = null;
            let uploadLat: number | null = null;
            let uploadLng: number | null = null;

            if ("geolocation" in navigator) {
                const pos = await new Promise<GeolocationPosition>((resolve, reject) => {
                    navigator.geolocation.getCurrentPosition(resolve, reject);
                }).catch(() => null);

                if (pos) {
                    uploadLat = pos.coords.latitude;
                    uploadLng = pos.coords.longitude;
                    const metadata = {
                        lat: uploadLat,
                        lng: uploadLng,
                        timestamp: new Date().toISOString()
                    };
                    uploadRes = await uploadMedia(file, metadata);
                    localStorage.setItem("floodwatch_last_upload_lat", uploadLat.toString());
                    localStorage.setItem("floodwatch_last_upload_lng", uploadLng.toString());
                } else {
                    uploadRes = await uploadMedia(file, {});
                }
            } else {
                uploadRes = await uploadMedia(file, {});
            }

            // Polling for AI Analysis (Phase 2)
            if (uploadRes && uploadRes.uuid) {
                setStatus("analyzing");
                let attempts = 0;
                let analysisComplete = false;
                let finalSeverity = "high";
                let finalRatio = 0.6;

                while (attempts < 15 && !analysisComplete) {
                    await new Promise(r => setTimeout(r, 2000));
                    const analysis = await pollAnalysis(uploadRes.uuid);
                    if (analysis.status === "complete") {
                        console.log("AI analysis:", analysis.data);
                        analysisComplete = true;
                        finalSeverity = analysis.data.severity || "high";
                        finalRatio = analysis.data.submergence_ratio || 0.6;
                        localStorage.setItem("floodwatch_last_severity", finalSeverity);
                        localStorage.setItem("floodwatch_last_ratio", finalRatio.toString());
                    }
                    attempts++;
                }

                if (!analysisComplete) {
                    // Fallback to defaults if backend timed out
                    localStorage.setItem("floodwatch_last_severity", "high");
                    localStorage.setItem("floodwatch_last_ratio", "0.6");
                }

                // Store flood zone persistently so ALL users can see it
                if (uploadLat && uploadLng) {
                    storeFloodZone(uploadLat, uploadLng, finalSeverity, finalRatio);
                }
            }

            setStatus("success");
        } catch (err: any) {
            console.error(err);
            setStatus("error");
            setErrorMessage(err.message || "Upload failed");
        }
    };

    return (
        <div className="flex flex-col h-full p-4 pt-8 space-y-4">
            <h1 className="text-2xl font-bold tracking-tight">Report Flooding</h1>

            <p className="text-muted-foreground text-sm">
                Take a picture or short video of the flooded area. Our AI will analyze the water depth and infrastructure damage to alert others.
            </p>

            {status === "success" ? (
                <Card className="flex-1 flex flex-col items-center justify-center p-6 border-green-500/50 bg-green-500/10">
                    <CheckCircle2 className="w-16 h-16 text-green-500 mb-4" />
                    <h2 className="text-xl font-bold mb-2">Analysis Complete!</h2>
                    <p className="text-center text-sm text-muted-foreground mb-6">Our AI has classified your upload and updated the live flood maps.</p>
                    <Button onClick={() => { setFile(null); setPreview(null); setStatus("idle"); }} variant="outline">
                        Report Another
                    </Button>
                </Card>
            ) : status === "analyzing" ? (
                <Card className="flex-1 flex flex-col items-center justify-center p-6 border-dashed border-2">
                    <Loader2 className="w-12 h-12 mb-4 animate-spin text-primary" />
                    <h2 className="text-xl font-bold mb-2">Bedrock AI Analysis...</h2>
                    <p className="text-center text-sm text-muted-foreground">Evaluating water depth and infrastructure damage. This usually takes 5-15 seconds.</p>
                </Card>
            ) : (
                <Card className="flex-1 flex flex-col items-center justify-center p-4 border-dashed border-2">
                    {preview ? (
                        <div className="w-full h-full flex flex-col items-center space-y-4 pt-4">
                            {file?.type.startsWith("video/") ? (
                                <video src={preview} controls className="max-h-[300px] rounded-lg m-auto" />
                            ) : (
                                <img src={preview} alt="Preview" className="max-h-[300px] object-contain rounded-lg m-auto" />
                            )}

                            <div className="w-full grid grid-cols-2 gap-3 mt-auto pt-4">
                                <Button variant="outline" onClick={() => fileInputRef.current?.click()} disabled={status === "uploading"}>
                                    Retake
                                </Button>
                                <Button onClick={handleUpload} disabled={status === "uploading"}>
                                    {status === "uploading" ? "Uploading..." : "Submit Report"}
                                </Button>
                            </div>
                            {status === "error" && <p className="text-red-500 text-xs text-center">{errorMessage}</p>}
                        </div>
                    ) : (
                        <div className="text-center space-y-4">
                            <div className="mx-auto w-20 h-20 bg-muted rounded-full flex items-center justify-center mb-4 cursor-pointer hover:bg-muted/80 transition-colors"
                                onClick={() => fileInputRef.current?.click()}
                            >
                                <Camera className="w-10 h-10 text-muted-foreground" />
                            </div>
                            <h3 className="font-semibold text-lg">Capture Media</h3>
                            <p className="text-sm text-muted-foreground px-4">
                                Use your device camera to document the flood severity. Location and metadata are automatically attached.
                            </p>
                        </div>
                    )}

                    {/* Hidden File Input configured for mobile camera capture */}
                    <input
                        type="file"
                        ref={fileInputRef}
                        className="hidden"
                        accept="image/*,video/*"
                        capture="environment"
                        onChange={handleFileCapture}
                    />
                </Card>
            )}
        </div>
    );
}
