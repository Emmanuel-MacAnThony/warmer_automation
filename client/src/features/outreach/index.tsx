import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { BatchView } from "./components/batch/BatchView";
import { CampaignListView } from "./components/CampaignListView";
import { CreateCampaignView } from "./components/CreateCampaignView";
import { NoTableSelected } from "./components/NoTableSelected";
import { QueueView } from "./components/QueueView";
import { SegmentingView } from "./components/SegmentingView";
import { OutreachContext } from "./context/OutreachContext";
import { useOutreach } from "./hooks/useOutreach";

export function Outreach() {
    const ctx = useOutreach();
    const navigate = useNavigate();
    const {
        baseId,
        tableId,
        activeCampaign,
        batchTier,
        batchFromDeepLink,
        setBatchFromDeepLink,
        loadCampaigns,
        setExpandedCard,
    } = ctx;

    if (!baseId || !tableId) return <NoTableSelected />;

    return (
        <OutreachContext.Provider value={ctx}>
            <Routes>
                <Route index element={<CampaignListView />} />
                <Route path="creating" element={<CreateCampaignView />} />
                <Route
                    path="segmenting"
                    element={
                        activeCampaign ? (
                            <SegmentingView />
                        ) : (
                            <Navigate to="/outreach" replace />
                        )
                    }
                />
                <Route
                    path="queue"
                    element={
                        activeCampaign ? (
                            <QueueView />
                        ) : (
                            <Navigate to="/outreach" replace />
                        )
                    }
                />
                <Route
                    path="batch"
                    element={
                        activeCampaign ? (
                            <BatchView
                                campaign={activeCampaign}
                                tier={batchTier}
                                initialStep={
                                    batchFromDeepLink ? "details" : "choose"
                                }
                                onBack={() => {
                                    setBatchFromDeepLink(false);
                                    if (batchFromDeepLink) {
                                        setExpandedCard({
                                            campaignId: activeCampaign.id,
                                            tier: batchTier,
                                        });
                                        navigate("/outreach");
                                    } else {
                                        navigate(-1);
                                    }
                                }}
                                onJobQueued={() => loadCampaigns()}
                            />
                        ) : (
                            <Navigate to="/outreach" replace />
                        )
                    }
                />
            </Routes>
        </OutreachContext.Provider>
    );
}
