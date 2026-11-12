import React from 'react';
import { cn } from '@/lib/utils';

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
}

export function Card({ className, children, ...props }: CardProps) {
  return (
    <div
      className={cn(
        'bg-white border border-[#E2E8F0] rounded-xl p-5 shadow-xs transition-all hover:border-[#CBD5E1] hover:shadow-sm',
        className
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-6 mb-6 border-b border-[#E2E8F0] gap-4">
      <div>
        <h1 className="text-2xl font-bold text-[#172B4D] tracking-tight">{title}</h1>
        {subtitle && <p className="text-sm text-[#64748B] mt-1">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-3">{actions}</div>}
    </div>
  );
}

export function MetricCard({
  label,
  value,
  subtitle,
  badgeText,
  badgeType = 'neutral',
  icon,
}: {
  label: string;
  value: string | number;
  subtitle?: string;
  badgeText?: string;
  badgeType?: 'success' | 'warning' | 'error' | 'info' | 'neutral';
  icon?: React.ReactNode;
}) {
  const badgeClasses = {
    success: 'bg-[#DCFCE7] text-[#16A34A] border-[#BBF7D0]',
    warning: 'bg-[#FEF3C7] text-[#D97706] border-[#FDE68A]',
    error: 'bg-[#FEE2E2] text-[#DC2626] border-[#FECACA]',
    info: 'bg-[#E0F2FE] text-[#0284C7] border-[#BAE6FD]',
    neutral: 'bg-[#F1F5F9] text-[#64748B] border-[#E2E8F0]',
  };

  return (
    <Card className="flex flex-col justify-between">
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-semibold uppercase tracking-wider text-[#64748B]">
          {label}
        </span>
        {badgeText && (
          <span
            className={cn(
              'px-2 py-0.5 text-xs font-medium rounded-full border',
              badgeClasses[badgeType]
            )}
          >
            {badgeText}
          </span>
        )}
      </div>
      <div className="flex items-baseline justify-between">
        <div className="text-3xl font-bold text-[#172B4D] tracking-tight">{value}</div>
        {icon && <div className="text-2xl text-[#94A3B8]">{icon}</div>}
      </div>
      {subtitle && <p className="text-xs text-[#64748B] mt-2">{subtitle}</p>}
    </Card>
  );
}

export function Badge({
  children,
  type = 'neutral',
  className,
}: {
  children: React.ReactNode;
  type?: 'success' | 'warning' | 'error' | 'info' | 'neutral';
  className?: string;
}) {
  const badgeClasses = {
    success: 'bg-[#DCFCE7] text-[#16A34A] border-[#BBF7D0]',
    warning: 'bg-[#FEF3C7] text-[#D97706] border-[#FDE68A]',
    error: 'bg-[#FEE2E2] text-[#DC2626] border-[#FECACA]',
    info: 'bg-[#E0F2FE] text-[#0284C7] border-[#BAE6FD]',
    neutral: 'bg-[#F1F5F9] text-[#64748B] border-[#E2E8F0]',
  };

  return (
    <span
      className={cn(
        'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border',
        badgeClasses[type],
        className
      )}
    >
      {children}
    </span>
  );
}
