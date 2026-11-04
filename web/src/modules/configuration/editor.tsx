/** 配置编辑器：把表单值转换成配置请求，版本字段防止覆盖其他管理员的新修改。 */
import { AgentClient } from "@factory-agent/chat";
import {
  Button,
  Drawer,
  Form,
  Input,
  InputNumber,
  Select,
  Switch,
  message,
} from "antd";
import { useState } from "react";

import { fieldLabels, templates, type Resource } from "./schema";

export function ResourceEditor({
  kind,
  row,
  client,
  onDone,
  onClose,
}: {
  kind: string;
  row?: Resource;
  client: AgentClient;
  onDone: () => void;
  onClose: () => void;
}) {
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);
  const defaults = { ...templates[kind], ...row?.config };
  delete defaults.has_url;
  delete defaults.has_api_key;
  const values: Record<string, any> = {
    id: row?.id ?? "",
    name: row?.name ?? "",
  };
  Object.entries(defaults).forEach(([k, v]) => {
    values[k] =
      (typeof v === "object" && !Array.isArray(v)) ||
      k === "joins" ||
      k === "cases"
        ? JSON.stringify(v, null, 2)
        : v;
  });
  const save = async () => {
    try {
      const result = await form.validateFields();
      setSaving(true);
      const config: Record<string, any> = {};
      Object.keys(defaults).forEach((key) => {
        const value = result[key];
        config[key] =
          (typeof defaults[key] === "object" &&
            !Array.isArray(defaults[key])) ||
          key === "joins" ||
          key === "cases"
            ? JSON.parse(value || "{}")
            : value;
      });
      if (kind === "topics" && !config.time_field) config.time_field = null;
      await client.json(
        `/admin/records/${kind}/${encodeURIComponent(result.id)}`,
        {
          method: "PUT",
          body: JSON.stringify({ ...result, config, version: row?.version }),
        },
      );
      message.success("配置已保存");
      onDone();
      onClose();
    } catch (e) {
      if (e instanceof Error) message.error(e.message);
    } finally {
      setSaving(false);
    }
  };
  return (
    <Drawer
      open
      title={row ? `编辑 · ${row.name}` : "新建配置"}
      width={620}
      onClose={onClose}
      extra={
        <Button type="primary" loading={saving} onClick={save}>
          保存配置
        </Button>
      }
    >
      <Form layout="vertical" form={form} initialValues={values}>
        <Form.Item
          name="id"
          label="唯一 ID"
          rules={[
            { required: true },
            {
              pattern: /^[A-Za-z0-9_-]{1,64}$/,
              message: "使用字母、数字、短横线或下划线",
            },
          ]}
        >
          <Input disabled={!!row} />
        </Form.Item>
        <Form.Item name="name" label="名称" rules={[{ required: true }]}>
          <Input />
        </Form.Item>
        {Object.entries(defaults).map(([key, value]) => (
          <Form.Item
            key={key}
            name={key}
            label={fieldLabels[key] ?? key}
            valuePropName={typeof value === "boolean" ? "checked" : "value"}
          >
            {typeof value === "boolean" ? (
              <Switch />
            ) : typeof value === "number" ? (
              <InputNumber style={{ width: "100%" }} />
            ) : Array.isArray(value) && !["joins", "cases"].includes(key) ? (
              <Select
                mode="tags"
                tokenSeparators={[","]}
                placeholder="输入 ID 后按 Enter"
              />
            ) : typeof value === "object" ||
              ["joins", "cases", "prompt", "description"].includes(key) ? (
              <Input.TextArea
                rows={["fields", "metrics", "cases"].includes(key) ? 7 : 4}
                style={
                  typeof value === "object" ? { fontFamily: "monospace" } : {}
                }
              />
            ) : ["url", "api_key"].includes(key) ? (
              <Input.Password
                autoComplete="off"
                placeholder="敏感配置加密保存"
              />
            ) : (
              <Input />
            )}
          </Form.Item>
        ))}
      </Form>
    </Drawer>
  );
}
