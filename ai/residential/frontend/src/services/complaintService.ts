/**
 * GridVision — Complaint Management Service
 * Provides client methods to fetch complaint categories, submit complaints with AI validation & scoring,
 * and list/retrieve customer complaints.
 */

import { apiClient } from '../../../../../frontend/src/services/apiClient';
import {
  Complaint,
  ComplaintCategory,
  SubmitComplaintPayload,
} from '../types/complaints';

export const complaintService = {
  /**
   * Fetch available complaint categories for the specified customer segment.
   */
  async getCategories(segment: string = 'RESIDENTIAL'): Promise<ComplaintCategory[]> {
    return apiClient.get<ComplaintCategory[]>('/complaints/categories', { segment });
  },

  /**
   * Fetch customer complaints with optional status filter ('REGISTERED', 'INVALID', etc.).
   */
  async getComplaints(statusFilter?: string): Promise<Complaint[]> {
    const params = statusFilter && statusFilter !== 'ALL' ? { status: statusFilter } : undefined;
    return apiClient.get<Complaint[]>('/complaints', params);
  },

  /**
   * Fetch full details for a specific complaint by ID.
   */
  async getComplaintDetail(complaintId: string): Promise<Complaint> {
    return apiClient.get<Complaint>(`/complaints/${encodeURIComponent(complaintId)}`);
  },

  /**
   * Submit a new complaint for AI validation and severity scoring.
   */
  async submitComplaint(payload: SubmitComplaintPayload): Promise<Complaint> {
    return apiClient.post<Complaint>('/complaints', payload, undefined, { timeoutMs: 60000 });
  },
};
