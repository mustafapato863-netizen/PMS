import { useParams } from 'react-router-dom';

export default function ReportPreviewView() {
  const { reportId } = useParams();

  return (
    <div className="flex h-[calc(100vh-6rem)] items-center justify-center text-slate-500">
      Report Preview Shell - {reportId}
    </div>
  );
}
