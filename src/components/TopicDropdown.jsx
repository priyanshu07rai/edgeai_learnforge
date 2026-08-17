import React from 'react';

/**
 * TopicDropdown Component (Mobile)
 * @param {Object} props
 * @param {Array} props.topics - List of topics
 * @param {number} props.activeTopicIdx - Currently active topic index
 * @param {Function} props.onTopicClick - Callback when topic is changed
 */
export default function TopicDropdown({ topics, activeTopicIdx, onTopicClick }) {
  if (!topics || topics.length === 0) return null;

  return (
    <div className="w-full bg-white dark:bg-[#111111] border-2 border-slate-300 dark:border-[#262626] rounded-2xl p-4 select-none shadow-md">
      <label htmlFor="topic-select" className="block text-xs font-black tracking-widest text-slate-500 dark:text-[#A3A3A3] uppercase mb-2">
        Knowledge Units
      </label>
      <select
        id="topic-select"
        value={activeTopicIdx !== null ? activeTopicIdx : ''}
        onChange={(e) => onTopicClick(Number(e.target.value))}
        className="w-full bg-slate-50 dark:bg-[#0B0B0B] border-2 border-slate-300 dark:border-[#262626] rounded-xl text-slate-900 dark:text-[#F5F5F5] py-2.5 px-3 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:focus:ring-[#7C3AED] text-sm cursor-pointer font-bold"
      >
        <option value={-1} className="bg-white text-slate-900 dark:bg-[#111111] dark:text-[#F5F5F5]">
          📌 Course Overview & Summary
        </option>
        {topics.map((topic, idx) => (
          <option key={idx} value={idx} className="bg-white text-slate-900 dark:bg-[#111111] dark:text-[#F5F5F5]">
            {topic.title} {topic.density_badge ? ` (${topic.density_badge})` : ''}
          </option>
        ))}
      </select>
    </div>
  );
}
