import React from "react";

interface ToastProps {
  message: string | null;
  type?: "error" | "info" | "success";
  onDismiss: () => void;
}

export const Toast: React.FC<ToastProps> = ({ message, type = "error", onDismiss }) => {
  if (!message) return null;

  const bgStyles = {
    error: "bg-red-600 text-white",
    info: "bg-gray-800 text-white",
    success: "bg-emerald-600 text-white",
  };

  return (
    <div
      className={`fixed bottom-5 right-5 z-50 flex items-center space-x-3 px-4 py-3 rounded-lg shadow-lg text-sm max-w-md transition-all duration-200 ${bgStyles[type]}`}
    >
      <div className="flex-1 font-medium">{message}</div>
      <button
        onClick={onDismiss}
        className="opacity-70 hover:opacity-100 transition-opacity text-lg leading-none font-bold ml-2"
        aria-label="Dismiss toast"
      >
        &times;
      </button>
    </div>
  );
};
