/** 知识资料页面：上传只创建后台作业，用户通过状态查看导入结果，不在浏览器中解析文档。 */
import { CloudUploadOutlined, ReloadOutlined } from "@ant-design/icons";
import { AgentClient } from "@factory-agent/chat";
import {
  Button,
  Card,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Upload,
  message,
} from "antd";
import { useCallback, useEffect, useState } from "react";

import { type Resource } from "../configuration/schema";

export function Documents({ client }: { client: AgentClient }) {
  const [rows, setRows] = useState<any[]>([]);
  const [kbs, setKbs] = useState<Resource[]>([]);
  const [kb, setKb] = useState<string>();
  const [busy, setBusy] = useState(false);
  const refresh = useCallback(async () => {
    try {
      const [d, k] = await Promise.all([
        client.json("/admin/documents"),
        client.json("/admin/records/knowledge-bases"),
      ]);
      setRows(d);
      setKbs(k);
      setKb((prev) => prev ?? k[0]?.id);
    } catch (e) {
      message.error(String(e));
    }
  }, [client]);
  useEffect(() => {
    refresh();
  }, [refresh]);
  return (
    <>
      <Card className="upload-card">
        <div>
          <h3>把系统知识带进来</h3>
          <p className="muted">
            支持文字
            PDF、DOCX、Markdown、TXT。后台自动切分、向量化并建立检索索引。
          </p>
        </div>
        <Space>
          <Select
            aria-label="目标知识库"
            placeholder="选择知识库"
            value={kb}
            onChange={setKb}
            style={{ width: 180 }}
            options={kbs.map((k) => ({ label: k.name, value: k.id }))}
          />
          <Upload
            accept="../../components/.pdf,.docx,.md,.txt"
            showUploadList={false}
            beforeUpload={async (file) => {
              if (!kb) return false;
              setBusy(true);
              try {
                const body = new FormData();
                body.append("kb_id", kb);
                body.append("file", file);
                const result = await client.json("/admin/documents", {
                  method: "POST",
                  body,
                });
                message.success(
                  result.duplicate ? "文件已存在" : "已上传，等待后台导入",
                );
                await refresh();
              } catch (e) {
                message.error(String(e));
              } finally {
                setBusy(false);
              }
              return false;
            }}
          >
            <Button
              type="primary"
              icon={<CloudUploadOutlined />}
              loading={busy}
              disabled={!kb}
            >
              上传文档
            </Button>
          </Upload>
        </Space>
      </Card>
      <div className="section-actions">
        <span>{rows.length} 份文档与版本</span>
        <Button icon={<ReloadOutlined />} onClick={refresh}>
          刷新状态
        </Button>
      </div>
      <Table
        rowKey="id"
        dataSource={rows}
        columns={[
          { title: "文档", dataIndex: "name" },
          { title: "知识库", dataIndex: "kb_id" },
          { title: "版本", dataIndex: "version" },
          {
            title: "状态",
            render: (_, r) => (
              <Tag
                color={
                  r.status === "ready"
                    ? "green"
                    : r.status === "failed"
                      ? "red"
                      : "default"
                }
              >
                {r.deleted ? "已删除" : r.status}
              </Tag>
            ),
          },
          { title: "异常说明", dataIndex: "error" },
          {
            title: "操作",
            render: (_, r) => (
              <Button
                danger
                type="text"
                disabled={r.deleted}
                onClick={() =>
                  Modal.confirm({
                    title: "删除此文档？",
                    content: "引用与检索立即停止访问。",
                    onOk: async () => {
                      await client.json(`/admin/documents/${r.id}`, {
                        method: "DELETE",
                      });
                      await refresh();
                    },
                  })
                }
              >
                删除
              </Button>
            ),
          },
        ]}
      />
    </>
  );
}
