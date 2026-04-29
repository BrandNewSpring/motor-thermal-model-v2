import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { profilesApi } from "@/lib/api";
import type { MotorProfileCreate, MotorProfileUpdate } from "@/types/motor";

export function useProfiles() {
  return useQuery({
    queryKey: ["profiles"],
    queryFn: () => profilesApi.list(),
  });
}

export function useProfile(id: string | null) {
  return useQuery({
    queryKey: ["profiles", id],
    queryFn: () => profilesApi.get(id!),
    enabled: !!id,
  });
}

export function useCreateProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: MotorProfileCreate) => profilesApi.create(data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["profiles"] });
    },
  });
}

export function useUpdateProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: MotorProfileUpdate }) =>
      profilesApi.update(id, data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["profiles"] });
    },
  });
}

export function useDeleteProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => profilesApi.delete(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["profiles"] });
    },
  });
}
