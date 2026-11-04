/** 配置资源页面：通过统一 API 展示、修改和测试资源，编辑行为委托给独立编辑器。 */
import { PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import { AgentClient } from "@factory-agent/chat";
import { Alert, Button, Modal, Space, Table, Tag, message } from "antd";
import { useCallback, useEffect, useState } from "react";

import { type Resource } from "./schema";
import { ResourceEditor } from "./editor";

export function Records({
  kind,
  client,
}: {
  kind: string;
  client: AgentClient;
}) {
  const [rows, setRows] = useState<Resource[]>([]);
  const [loading, setLoading] = useState(true);
  const [editor, setEditor] = useState<Resource | null | undefined>();
  const [report, setReport] = useState<any>();
  const [evaluating, setEvaluating] = useState(false);
  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setRows(await client.json(`/admin/records/${kind}`));
    } catch (e) {
      message.error(String(e));
    } finally {
      setLoading(false);
    }
  }, [kind, client]);
  useEffect(() => {
    refresh();
  }, [refresh]);
  const action = async (row: Resource, type: string) => {
    try {
      if (type === "delete") {
        await client.json(`/admin/records/${kind}/${row.id}`, {
          method: "DELETE",
        });
        await refresh();
      }
      if (type === "test") {
        const result = await client.json(`/admin/models/${row.id}/test`, {
          method: "POST",
        });
        message.success(
          `连接正常，向量维度 ${result.embedding_dimension}，流式输出正常`,
        );
      }
      if (type === "reindex") {
        await client.json(`/admin/knowledge-bases/${row.id}/reindex`, {
          method: "POST",
        });
        message.success("重建任务已排队");
      }
      if (type === "evaluate") {
        setEvaluating(true);
        setReport(
          await client.json(`/admin/evaluations/${row.id}/run`, {
            method: "POST",
          }),
        );
      }
    } catch (e) {
      message.error(String(e));
    } finally {
      setEvaluating(false);
    }
  };
  return (
    <>
      <div className="section-actions">
        <span>{rows.length} 项配置 · 权限变更实时生效</span>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={refresh}>
            刷新
          </Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setEditor(null)}
          >
            新建
          </Button>
        </Space>
      </div>
      {kind === "topics" && (
        <Alert
          showIcon
          type="info"
          message="仅配置允许查询的字段、关联和指标；启用前必须设置部门权限字段。"
          style={{ marginBottom: 16 }}
        />
      )}
      <Table
        loading={loading}
        rowKey="id"
        dataSource={rows}
        pagination={{ pageSize: 10 }}
        columns={[
          {
            title: "名称 / ID",
            key: "name",
            render: (_, r) => (
              <>
                <strong>{r.name}</strong>
                <div className="muted tiny">{r.id}</div>
              </>
            ),
          },
          {
            title: "状态",
            key: "state",
            render: (_, r) => (
              <Tag color={r.config.enabled === false ? "default" : "green"}>
                {r.config.enabled === false ? "停用" : "可用"}
              </Tag>
            ),
          },
          {
            title: "访问范围",
            key: "acl",
            render: (_, r) => (
              <Space wrap>
                {(r.config.roles ?? []).map((v: string) => (
                  <Tag key={v}>{v}</Tag>
                ))}
                {(r.config.departments ?? []).map((v: string) => (
                  <Tag key={v} color="blue">
                    {v}
                  </Tag>
                ))}
              </Space>
            ),
          },
          { title: "版本", dataIndex: "version", width: 80 },
          {
            title: "操作",
            key: "actions",
            render: (_, r) => (
              <Space>
                <Button type="link" onClick={() => setEditor(r)}>
                  编辑
                </Button>
                {kind === "models" && (
                  <Button type="link" onClick={() => action(r, "test")}>
                    测试接口
                  </Button>
                )}
                {kind === "knowledge-bases" && (
                  <Button type="link" onClick={() => action(r, "reindex")}>
                    重建索引
                  </Button>
                )}
                {kind === "evaluations" && (
                  <Button
                    type="link"
                    loading={evaluating}
                    onClick={() => action(r, "evaluate")}
                  >
                    运行评测
                  </Button>
                )}
                <Button
                  type="text"
                  danger
                  onClick={() =>
                    Modal.confirm({
                      title: `删除“${r.name}”？`,
                      content: "关联资源可能停止可用。",
                      onOk: () => action(r, "delete"),
                    })
                  }
                >
                  删除
                </Button>
              </Space>
            ),
          },
        ]}
      />
      {editor !== undefined && (
        <ResourceEditor
          key={`${kind}:${editor?.id}`}
          kind={kind}
          row={editor ?? undefined}
          client={client}
          onDone={refresh}
          onClose={() => setEditor(undefined)}
        />
      )}
      <Modal
        open={!!report}
        title={`评测结果：${report?.passed}/${report?.total}`}
        footer={null}
        width={800}
        onCancel={() => setReport(undefined)}
      >
        <Table
          rowKey="question"
          dataSource={report?.cases}
          columns={[
            { title: "问题", dataIndex: "question" },
            { title: "路由", dataIndex: "route" },
            {
              title: "通过",
              dataIndex: "passed",
              render: (v) => (v ? "通过" : "失败"),
            },
            { title: "耗时（秒）", dataIndex: "seconds" },
          ]}
        />
      </Modal>
    </>
  );
}
