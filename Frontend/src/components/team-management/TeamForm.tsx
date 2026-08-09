/**
 * Team Form Component
 * Form for creating and editing teams.
 */

import { useState } from 'react';
import { motion } from 'framer-motion';
import { ArrowLeft } from 'lucide-react';

export interface TeamFormData {
  name: string;
  display_name: string;
  region: string;
  description: string;
  kpi_keys: string[];
  kpi_weights: Record<string, number>;
  team_lead: string;
  team_lead_email: string;
}

interface TeamFormProps {
  mode: 'create' | 'edit';
  initialData?: Partial<TeamFormData>;
  onSubmit: (data: TeamFormData) => void | Promise<void>;
  onCancel: () => void;
  isLoading?: boolean;
}

const KPI_OPTIONS = ['attendance', 'productivity', 'quality', 'punctuality', 'accuracy'];
const REGION_OPTIONS = ['EGY', 'UAE', 'Other'];

export function TeamForm({ mode, initialData, onSubmit, onCancel, isLoading }: TeamFormProps) {
  const [formData, setFormData] = useState<TeamFormData>({
    name: initialData?.name || '',
    display_name: initialData?.display_name || '',
    region: initialData?.region || 'EGY',
    description: initialData?.description || '',
    kpi_keys: initialData?.kpi_keys || ['attendance', 'productivity', 'quality'],
    kpi_weights: initialData?.kpi_weights || {
      attendance: 0.3,
      productivity: 0.4,
      quality: 0.3,
    },
    team_lead: initialData?.team_lead || '',
    team_lead_email: initialData?.team_lead_email || '',
  });

  const [errors, setErrors] = useState<Record<string, string>>({});
  const [selectedKpis, setSelectedKpis] = useState<string[]>(formData.kpi_keys);

  // Validate form
  const validateForm = () => {
    const newErrors: Record<string, string> = {};

    if (!formData.name.trim()) {
      newErrors.name = 'Team name is required';
    } else if (!/^[a-z0-9_]+$/.test(formData.name)) {
      newErrors.name = 'Only lowercase letters, numbers, and underscores';
    }

    if (!formData.display_name.trim()) {
      newErrors.display_name = 'Display name is required';
    }

    if (selectedKpis.length === 0) {
      newErrors.kpi_keys = 'At least one KPI is required';
    }

    // Validate KPI weights sum to 1.0
    const totalWeight = Object.values(formData.kpi_weights).reduce((a, b) => a + (b || 0), 0);
    if (Math.abs(totalWeight - 1.0) > 0.01) {
      newErrors.kpi_weights = `KPI weights must sum to 1.0 (current: ${totalWeight.toFixed(2)})`;
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validateForm()) return;

    const dataToSubmit = {
      ...formData,
      kpi_keys: selectedKpis,
      kpi_weights: Object.fromEntries(
        selectedKpis.map((kpi) => [kpi, formData.kpi_weights[kpi] || 0.33])
      ),
    };

    await onSubmit(dataToSubmit);
  };

  const handleKpiToggle = (kpi: string) => {
    setSelectedKpis((prev) =>
      prev.includes(kpi) ? prev.filter((k) => k !== kpi) : [...prev, kpi]
    );
  };

  const handleWeightChange = (kpi: string, value: number) => {
    setFormData((prev) => ({
      ...prev,
      kpi_weights: {
        ...prev.kpi_weights,
        [kpi]: value,
      },
    }));
  };

  const weightSum = Object.entries(formData.kpi_weights)
    .filter(([kpi]) => selectedKpis.includes(kpi))
    .reduce((sum, [, weight]) => sum + (weight || 0), 0);

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="max-w-2xl"
    >
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <motion.button
          whileHover={{ scale: 1.1 }}
          whileTap={{ scale: 0.9 }}
          onClick={onCancel}
          className="p-2 text-[var(--text-muted)] hover:text-[var(--text-primary)]
            hover:bg-[var(--bg-sunken)] rounded-lg transition-all"
        >
          <ArrowLeft size={20} />
        </motion.button>
        <div>
          <h2 className="text-2xl font-bold text-[var(--text-primary)]">
            {mode === 'create' ? 'Create New Team' : 'Edit Team'}
          </h2>
          <p className="text-sm text-[var(--text-muted)]">
            {mode === 'create'
              ? 'Configure a new team and set up performance metrics'
              : 'Update team configuration and metrics'}
          </p>
        </div>
      </div>

      {/* Form */}
      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Basic Info */}
        <div className="bg-[var(--bg-surface)]/60 rounded-xl p-6 border border-[var(--border-light)]">
          <h3 className="font-semibold text-[var(--text-primary)] mb-4">Team Information</h3>

          <div className="space-y-4">
            {/* Team Name */}
            <div>
              <label className="block text-sm font-medium text-[var(--text-secondary)] mb-2">
                Team Name *
              </label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) =>
                  setFormData((prev) => ({
                    ...prev,
                    name: e.target.value.toLowerCase().replace(/\s+/g, '_'),
                  }))
                }
                disabled={mode === 'edit'}
                placeholder="inbound_team"
                className="w-full px-4 py-2 bg-[var(--bg-base)] border border-[var(--border-light)]
                  rounded-lg text-[var(--text-primary)] placeholder-[var(--text-muted)]
                  focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
              />
              {errors.name && <p className="text-xs text-red-600 mt-1">{errors.name}</p>}
            </div>

            {/* Display Name */}
            <div>
              <label className="block text-sm font-medium text-[var(--text-secondary)] mb-2">
                Display Name *
              </label>
              <input
                type="text"
                value={formData.display_name}
                onChange={(e) =>
                  setFormData((prev) => ({ ...prev, display_name: e.target.value }))
                }
                placeholder="Inbound Team"
                className="w-full px-4 py-2 bg-[var(--bg-base)] border border-[var(--border-light)]
                  rounded-lg text-[var(--text-primary)] placeholder-[var(--text-muted)]
                  focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              {errors.display_name && (
                <p className="text-xs text-red-600 mt-1">{errors.display_name}</p>
              )}
            </div>

            {/* Region */}
            <div>
              <label className="block text-sm font-medium text-[var(--text-secondary)] mb-2">
                Region
              </label>
              <select
                value={formData.region}
                onChange={(e) => setFormData((prev) => ({ ...prev, region: e.target.value }))}
                className="w-full px-4 py-2 bg-[var(--bg-base)] border border-[var(--border-light)]
                  rounded-lg text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {REGION_OPTIONS.map((region) => (
                  <option key={region} value={region}>
                    {region}
                  </option>
                ))}
              </select>
            </div>

            {/* Description */}
            <div>
              <label className="block text-sm font-medium text-[var(--text-secondary)] mb-2">
                Description
              </label>
              <textarea
                value={formData.description}
                onChange={(e) =>
                  setFormData((prev) => ({ ...prev, description: e.target.value }))
                }
                placeholder="Team description..."
                rows={3}
                className="w-full px-4 py-2 bg-[var(--bg-base)] border border-[var(--border-light)]
                  rounded-lg text-[var(--text-primary)] placeholder-[var(--text-muted)]
                  focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
              />
            </div>
          </div>
        </div>

        {/* Team Lead */}
        <div className="bg-[var(--bg-surface)]/60 rounded-xl p-6 border border-[var(--border-light)]">
          <h3 className="font-semibold text-[var(--text-primary)] mb-4">Team Lead</h3>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-[var(--text-secondary)] mb-2">
                Name
              </label>
              <input
                type="text"
                value={formData.team_lead}
                onChange={(e) => setFormData((prev) => ({ ...prev, team_lead: e.target.value }))}
                placeholder="Ahmed Hassan"
                className="w-full px-4 py-2 bg-[var(--bg-base)] border border-[var(--border-light)]
                  rounded-lg text-[var(--text-primary)] placeholder-[var(--text-muted)]
                  focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-[var(--text-secondary)] mb-2">
                Email
              </label>
              <input
                type="email"
                value={formData.team_lead_email}
                onChange={(e) =>
                  setFormData((prev) => ({ ...prev, team_lead_email: e.target.value }))
                }
                placeholder="ahmed@company.com"
                className="w-full px-4 py-2 bg-[var(--bg-base)] border border-[var(--border-light)]
                  rounded-lg text-[var(--text-primary)] placeholder-[var(--text-muted)]
                  focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>
        </div>

        {/* KPI Configuration */}
        <div className="bg-[var(--bg-surface)]/60 rounded-xl p-6 border border-[var(--border-light)]">
          <h3 className="font-semibold text-[var(--text-primary)] mb-4">Performance KPIs *</h3>

          {errors.kpi_keys && <p className="text-xs text-red-600 mb-3">{errors.kpi_keys}</p>}

          {/* KPI Selection */}
          <div className="mb-6">
            <label className="block text-xs font-semibold text-[var(--text-secondary)] uppercase mb-3">
              Select KPIs
            </label>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
              {KPI_OPTIONS.map((kpi) => (
                <motion.button
                  key={kpi}
                  type="button"
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={() => handleKpiToggle(kpi)}
                  className={`px-4 py-2 rounded-lg font-medium text-sm transition-all ${
                    selectedKpis.includes(kpi)
                      ? 'bg-blue-600 text-white'
                      : 'bg-[var(--bg-base)] text-[var(--text-secondary)] border border-[var(--border-light)]'
                  }`}
                >
                  {kpi.charAt(0).toUpperCase() + kpi.slice(1)}
                </motion.button>
              ))}
            </div>
          </div>

          {/* KPI Weights */}
          {selectedKpis.length > 0 && (
            <div>
              <label className="block text-xs font-semibold text-[var(--text-secondary)] uppercase mb-3">
                Weight Distribution ({weightSum.toFixed(2)})
              </label>
              <div className="space-y-3">
                {selectedKpis.map((kpi) => (
                  <div key={kpi}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm font-medium text-[var(--text-secondary)] capitalize">
                        {kpi}
                      </span>
                      <span className="text-xs font-semibold text-blue-600">
                        {(formData.kpi_weights[kpi] || 0).toFixed(1)}%
                      </span>
                    </div>
                    <input
                      type="range"
                      min="0"
                      max="100"
                      step="5"
                      value={(formData.kpi_weights[kpi] || 0) * 100}
                      onChange={(e) => handleWeightChange(kpi, parseFloat(e.target.value) / 100)}
                      className="w-full h-2 bg-[var(--bg-base)] rounded-lg appearance-none cursor-pointer"
                    />
                  </div>
                ))}
              </div>
              {errors.kpi_weights && (
                <p className="text-xs text-red-600 mt-3">{errors.kpi_weights}</p>
              )}
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-3 pt-4 border-t border-[var(--border-light)]">
          <motion.button
            type="button"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={onCancel}
            disabled={isLoading}
            className="flex-1 px-4 py-2.5 bg-[var(--bg-base)] border border-[var(--border-light)]
              text-[var(--text-secondary)] font-semibold rounded-lg hover:bg-[var(--bg-sunken)]
              transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Cancel
          </motion.button>

          <motion.button
            type="submit"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            disabled={isLoading}
            className="flex-1 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white font-semibold
              rounded-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading ? 'Saving...' : mode === 'create' ? 'Create Team' : 'Update Team'}
          </motion.button>
        </div>
      </form>
    </motion.div>
  );
}

export default TeamForm;
