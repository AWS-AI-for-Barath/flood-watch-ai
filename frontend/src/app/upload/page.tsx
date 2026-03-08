"use client";

import { useState } from "react";
import { Camera, Image as ImageIcon, UploadCloud } from "lucide-react";
import { apiStore } from "@/lib/api";

export default function UploadPage() {
    const [file, setFile] = useState<File | null>(null);
    const [loading, setLoading] = useState(false);
    const [success, setSuccess] = useState(false);

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files && e.target.files[0]) {
            setFile(e.target.files[0]);
            setSuccess(false);
        }
    };

    const uploadToS3 = async (url: string, file: File) => {
        const res = await fetch(url, {
            method: "PUT",
            headers: { "Content-Type": file.type },
            body: file
        });
        if (!res.ok) throw new Error("S3 Upload Failed");
    };

    const handleSubmit = async () => {
        if (!file) return;
        setLoading(true);
        try {
            // 1. Get Presigned URLs
            const { mediaUrl, metadataUrl } = await apiStore.getUploadTokens(file.name, file.type);

            // 2. Upload Media
            await uploadToS3(mediaUrl, file);

            // 3. Upload Metadata (mocking telemetry for brevity)
            const metadata = {
                timestamp: new Date().toISOString(),
                lat: 13.08,
                lon: 80.27,
                device: "mobile-pwa",
                filename: file.name
            };

            const metaBlob = new Blob([JSON.stringify(metadata)], { type: "application/json" });
            await uploadToS3(metadataUrl, metaBlob as File);

            setSuccess(true);
            setFile(null);
        } catch (err) {
            console.error(err);
            alert("Upload failed. Offline queuing will trigger.");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="flex flex-col gap-6 pb-8">
            <div className="px-2 pt-2">
                <h1 className="text-3xl font-bold tracking-tight">Report Flood</h1>
                <p className="text-sm text-gray-500 mt-1">Upload media to help route emergency services.</p>
            </div>

            <section className="minimal-card flex flex-col items-center justify-center p-8 gap-4 border-dashed border-2 bg-gray-50/50 hover:bg-gray-50 transition-colors">
                {file ? (
                    <div className="flex flex-col items-center text-center gap-2">
                        <div className="w-16 h-16 bg-blue-100 text-blue-600 rounded-full flex items-center justify-center">
                            <UploadCloud size={32} />
                        </div>
                        <span className="text-sm font-semibold truncate max-w-[200px]">{file.name}</span>
                        <button onClick={() => setFile(null)} className="text-xs text-red-500 font-medium">Remove</button>
                    </div>
                ) : (
                    <>
                        <div className="flex gap-4">
                            <label className="flex flex-col items-center justify-center w-20 h-20 bg-white border border-gray-100 shadow-sm rounded-2xl cursor-pointer active:scale-95 transition-transform text-black">
                                <Camera size={28} className="mb-1" strokeWidth={1.5} />
                                <span className="text-[10px] font-semibold uppercase tracking-wider">Camera</span>
                                <input type="file" accept="image/*,video/*" capture="environment" className="hidden" onChange={handleFileChange} />
                            </label>

                            <label className="flex flex-col items-center justify-center w-20 h-20 bg-white border border-gray-100 shadow-sm rounded-2xl cursor-pointer active:scale-95 transition-transform text-black">
                                <ImageIcon size={28} className="mb-1" strokeWidth={1.5} />
                                <span className="text-[10px] font-semibold uppercase tracking-wider">Gallery</span>
                                <input type="file" accept="image/*,video/*" className="hidden" onChange={handleFileChange} />
                            </label>
                        </div>
                    </>
                )}
            </section>

            {success && (
                <div className="bg-green-50 text-green-700 p-4 rounded-xl text-sm font-medium flex items-center gap-2">
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
                    Report successfully uploaded.
                </div>
            )}

            <button
                onClick={handleSubmit}
                disabled={!file || loading}
                className="w-full bg-black text-white rounded-2xl px-4 py-4 font-semibold text-base transition-transform active:scale-95 disabled:opacity-30 disabled:active:scale-100"
            >
                {loading ? "Transmitting..." : "Submit Report"}
            </button>
        </div>
    );
}
