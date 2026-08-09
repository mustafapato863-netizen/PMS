import { useSearchParams } from 'react-router-dom';
import type { PreApprovalsWorkflowFilter } from '../types';

const WORKFLOW_VALUES: PreApprovalsWorkflowFilter[] = ['all', 'ip_final', 'op_final', 'ip_elective'];

export function usePreApprovalsWorkflowParam(defaultWorkflow: PreApprovalsWorkflowFilter = 'all') {
  const [searchParams, setSearchParams] = useSearchParams();
  const raw = searchParams.get('workflow') as PreApprovalsWorkflowFilter | null;
  const workflow = raw && WORKFLOW_VALUES.includes(raw) ? raw : defaultWorkflow;

  const setWorkflow = (next: PreApprovalsWorkflowFilter) => {
    const params = new URLSearchParams(searchParams);
    if (next === 'all') params.delete('workflow');
    else params.set('workflow', next);
    setSearchParams(params);
  };

  return { workflow, setWorkflow };
}

