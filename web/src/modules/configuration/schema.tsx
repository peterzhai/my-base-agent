/** 展示配置与表单模板，不包含权限决策；真正权限始终由服务端执行。 */
import {
  ApartmentOutlined,
  BookOutlined,
  CloudUploadOutlined,
  DatabaseOutlined,
  ExperimentOutlined,
  MessageOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  SettingOutlined,
} from "@ant-design/icons";

export type Resource = {
  id: string;
  name: string;
  config: Record<string, any>;
  version: number;
  updated_at?: string;
};
export const sections = [
  { key: "overview", label: "工作台", icon: <ApartmentOutlined /> },
  { key: "chat", label: "问答调试", icon: <MessageOutlined /> },
  { key: "knowledge-bases", label: "知识库", icon: <BookOutlined /> },
  { key: "documents", label: "文档与索引", icon: <CloudUploadOutlined /> },
  { key: "topics", label: "业务主题", icon: <DatabaseOutlined /> },
  { key: "datasources", label: "数据源", icon: <DatabaseOutlined /> },
  { key: "agents", label: "Agent 配置", icon: <ApartmentOutlined /> },
  { key: "models", label: "模型服务", icon: <SettingOutlined /> },
  { key: "users", label: "用户", icon: <SafetyCertificateOutlined /> },
  { key: "roles", label: "角色", icon: <SafetyCertificateOutlined /> },
  { key: "departments", label: "部门", icon: <ApartmentOutlined /> },
  {
    key: "identity-maps",
    label: "宿主身份映射",
    icon: <SafetyCertificateOutlined />,
  },
  { key: "jobs", label: "后台任务", icon: <ReloadOutlined /> },
  { key: "audits", label: "审计与反馈", icon: <SafetyCertificateOutlined /> },
  { key: "evaluations", label: "评测集", icon: <ExperimentOutlined /> },
];
export const templates: Record<string, any> = {
  "knowledge-bases": {
    enabled: true,
    roles: ["employee"],
    departments: ["workshop-a"],
  },
  agents: {
    enabled: true,
    model_id: "default",
    roles: ["employee"],
    max_steps: 24,
    timeout_seconds: 90,
    prompt: "你是工厂内网问答助手。",
    kb_ids: ["manuals"],
    topic_ids: ["production", "inventory"],
  },
  models: {
    enabled: true,
    provider: "openai-compatible",
    base_url: "http://model.internal:8000/v1",
    chat_model: "",
    embedding_model: "",
    api_key: "",
  },
  datasources: {
    enabled: true,
    roles: ["employee"],
    departments: ["workshop-a"],
    url: "",
  },
  topics: {
    enabled: false,
    roles: ["employee"],
    departments: ["workshop-a"],
    datasource_id: "",
    table: "",
    alias: "t",
    fields: { department: "t.department" },
    dimensions: {},
    metrics: {},
    joins: [],
    department_field: "department",
    time_field: "",
    description: "",
  },
  users: { enabled: true, department: "workshop-a", roles: ["employee"] },
  roles: {},
  departments: {},
  "identity-maps": { enabled: true, external_id: "", user_id: "" },
  evaluations: {
    agent_id: "factory",
    cases: [
      {
        question: "MES 如何报工？",
        expected_route: "knowledge",
        require_citations: true,
      },
    ],
  },
};
export const fieldLabels: Record<string, string> = {
  enabled: "启用",
  roles: "允许角色",
  departments: "允许部门",
  department: "所属部门",
  model_id: "模型配置 ID",
  kb_ids: "可用知识库 ID",
  topic_ids: "可用业务主题 ID",
  max_steps: "执行步数预算",
  timeout_seconds: "执行超时（秒）",
  prompt: "系统提示词",
  provider: "模型协议",
  base_url: "模型服务地址",
  chat_model: "聊天模型标识",
  embedding_model: "向量模型标识",
  api_key: "模型密钥（留空保持原值）",
  url: "数据库连接串（留空保持原值）",
  datasource_id: "数据源 ID",
  table: "主表",
  alias: "主表别名",
  fields: "字段白名单：键 → 表别名.列名",
  dimensions: "维度：字段键 → 显示名",
  metrics: "指标定义",
  joins: "预配置表关联",
  department_field: "部门权限字段键",
  time_field: "时间字段键",
  description: "业务口径说明",
  external_id: "宿主用户标识",
  user_id: "平台用户 ID",
  agent_id: "被测 Agent ID",
  cases: "评测案例",
};
